from base64 import urlsafe_b64encode
from itertools import groupby
import os
from functools import lru_cache
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm.collections import attribute_mapped_collection, collection

from .. import db
from . import AuthMethod, PermissionType
from ..util import AutoID, Timestamped, AutoName
from ..models import Action, Modifier, Request


users_groups = db.Table('users_groups', db.Model.metadata,
        db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
        db.Column('group_id', db.Integer, db.ForeignKey('group.id')))


@lru_cache()
def _cached_has_permission(entity_id, permissions, division_id):
    """Caches the results of permissions checks for entities."""
    entity = Entity.query.get(entity_id)
    perms = entity.permissions.filter(Permission.permission.in_(permissions))
    if division_id is not None:
        division = Division.query.get(division_id)
        perms = perms.filter_by(division=division)
    return db.session.query(perms.exists()).all()[0][0]


class Entity(db.Model, AutoID, AutoName):
    """Private class for shared functionality between :py:class:`User` and
    :py:class:`Group`.

    This class defines a number of helper methods used indirectly by User and
    Group subclasses such as automatically defining the table name and mapper
    arguments.

    You should `not` inherit fomr this class directly, and should instead
    inherit from either :py:class:`User` or :py:class:`Group`.
    """

    #: The name of the entity. Usually a nickname.
    name = db.Column(db.String(100), nullable=False)

    #: Polymorphic discriminator column.
    type_ = db.Column(db.String(50))

    #: :py:class:`Permission`\s associated specifically with this entity.
    entity_permissions = db.relationship('Permission', collection_class=set,
            back_populates='entity', lazy='dynamic')

    #: The name of the :py:class:`AuthMethod` for this entity.
    authmethod = db.Column(db.String(50), nullable=False)

    @declared_attr
    def __mapper_args__(cls):
        """SQLAlchemy late-binding attribute to set mapper arguments.

        Obviates subclasses from having to specify polymorphic identities.
        """
        args = {'polymorphic_identity': cls.__name__}
        if cls.__name__ == 'Entity':
            args['polymorphic_on'] = cls.type_
        return args

    def __init__(self, name, authmethod, **kwargs):
        self.name = name
        self.authmethod = authmethod
        super(Entity, self).__init__(**kwargs)

    def __repr__(self):
        return "{x.__class__.__name__}('{x.name}')".format(x=self)

    def __str__(self):
        return "{x.name}".format(x=self)

    def has_permission(self, permissions, division_or_request=None):
        """Returns if this entity has been granted a permission in a division.

        If ``division`` is ``None``, this method checks if this group has the
        given permission in `any` division.

        :param permissions: The series of permissions to check
        :type permissions: iterable
        :param division_or_request: The division to check. May also be ``None``
            or an SRP request.
        :type division: :py:class:`Division` or :py:class:`~.models.Request`
        :rtype bool:
        """
        if permissions in PermissionType.all:
            permissions = (permissions,)
        # admin permission includes the reviewer and payer privileges
        if PermissionType.admin not in permissions and \
                PermissionType.elevated.issuperset(permissions):
            if self.has_permission(PermissionType.admin, division_or_request):
                return True
        if division_or_request is not None:
            # requests have a 'division' attribute, so we check for that
            if hasattr(division_or_request, 'division'):
                division_id = division_or_request.division.id
            else:
                division_id = division_or_request.id
        else:
            division_id = None
        permissions = frozenset(permissions)
        return _cached_has_permission(self.id, permissions, division_id)


class APIKey(db.Model, AutoID, AutoName, Timestamped):

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    user = db.relationship('User', back_populates='api_keys')

    key = db.Column(db.LargeBinary(32), nullable=False)

    def __init__(self, user):
        self.user = user
        self.key = os.urandom(32)

    @property
    def hex_key(self):
        return urlsafe_b64encode(self.key).decode('utf-8').replace('=', ',')


class User(Entity):
    """User base class.

    Represents users who can submit, review and/or pay out requests. It also
    supplies a number of convenience methods for subclasses.
    """
    id = db.Column(db.Integer, db.ForeignKey('entity.id'), primary_key=True)

    #: If the user is an administrator. This allows the user to create and
    #: administer divisions.
    admin = db.Column(db.Boolean, nullable=False, default=False)

    #: :py:class:`~.Request`\s this user has submitted.
    requests = db.relationship(Request, back_populates='submitter')

    #: :py:class:`~.Action`\s this user has performed on requests.
    actions = db.relationship(Action, back_populates='user')

    #: :py:class:`~.Pilot`\s associated with this user.
    pilots = db.relationship('Pilot', back_populates='user',
            collection_class=set)

    #: :py:class:`Group`\s this user is a member of
    groups = db.relationship('Group', secondary=users_groups,
            back_populates='users', collection_class=set)

    notes = db.relationship('Note', back_populates='user',
            order_by='desc(Note.timestamp)', foreign_keys='Note.user_id')

    notes_made = db.relationship('Note', back_populates='noter',
            order_by='desc(Note.timestamp)', foreign_keys='Note.noter_id')

    api_keys = db.relationship(APIKey, back_populates='user')

    @hybrid_property
    def permissions(self):
        """All :py:class:`Permission` objects associated with this user."""
        groups = db.session.query(users_groups.c.group_id.label('group_id'))\
                .filter(users_groups.c.user_id==self.id).subquery()
        group_perms = db.session.query(Permission)\
                .join(groups, groups.c.group_id==Permission.entity_id)
        user_perms = db.session.query(Permission)\
                .join(User)\
                .filter(User.id==self.id)
        perms = user_perms.union(group_perms)
        return perms

    @permissions.expression
    def permissions(cls):
        groups = db.select([users_groups.c.group_id])\
                .where(users_groups.c.user_id==cls.id).alias()
        group_permissions = db.select([Permission])\
                .where(Permission.entity_id.in_(groups)).alias()
        user_permissions = db.select([Permission])\
                .where(Permission.entity_id==cls.id)
        return user_permissions.union(group_permissions)

    def is_authenticated(self):
        """Part of the interface for Flask-Login."""
        return True

    def is_active(self):
        """Part of the interface for Flask-Login."""
        return True

    def is_anonymous(self):
        """Part of the interface for Flask-Login."""
        return False

    def get_id(self):
        """Part of the interface for Flask-Login."""
        return str(self.id)

    def submit_divisions(self):
        """Get a list of the divisions this user is able to submit requests to.

        :returns: A list of tuples. The tuples are in the form (division.id,
            division.name)
        :rtype: list
        """
        submit_perms = self.permissions\
                .filter_by(permission=PermissionType.submit)\
                .subquery()
        divisions = db.session.query(Division).join(submit_perms)\
                .order_by(Division.name)
        # Remove duplicates and sort divisions by name
        choices = []
        for name, group in groupby(divisions, lambda d: d.name):
            choices.append((next(group).id, name))
        return choices


class Note(db.Model, AutoID, Timestamped, AutoName):
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship(User, back_populates='notes',
            foreign_keys=[user_id])
    content = db.Column(db.Text, nullable=False)
    noter_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    noter = db.relationship(User, back_populates='notes_made',
            foreign_keys=[noter_id])

    def __init__(self, user, noter, note):
        self.user = user
        self.noter = noter
        self.content = note


class Pilot(db.Model, AutoID, AutoName):
    """Represents an in-game character."""

    #: The name of the character
    name = db.Column(db.String(150), nullable=False)

    #: The id of the User this character belongs to.
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    #: The User this character belongs to.
    user = db.relationship(User, back_populates='pilots')

    #: The Requests filed with lossmails from this character.
    requests = db.relationship(Request, back_populates='pilot',
            collection_class=list, order_by=Request.timestamp.desc())

    def __init__(self, user, name, id_):
        """Create a new Pilot instance.

        :param user: The user this character belpongs to.
        :type user: :py:class:`~.User`
        :param str name: The name of this character.
        :param int id_: The CCP-given characterID number.
        """
        self.user = user
        self.name = name
        self.id = id_

    def __repr__(self):
        return "{x.__class__.__name__}({x.user}, '{x.name}', {x.id})".format(
                x=self)

    def __str__(self):
        return self.name


class Group(Entity):
    """Base class for a group of users.

    Represents a group of users. Usable for granting permissions to submit,
    evaluate and pay.
    """

    id = db.Column(db.Integer, db.ForeignKey('entity.id'), primary_key=True)

    #: :py:class:`User` s that belong to this group.
    users = db.relationship(User, secondary=users_groups,
            back_populates='groups', collection_class=set)

    #: Synonym for :py:attr:`entity_permissions`
    permissions = db.synonym('entity_permissions')


class Permission(db.Model, AutoID, AutoName):
    __table_args__ = (
        db.UniqueConstraint('division_id', 'entity_id', 'permission'),
    )

    division_id = db.Column(db.Integer, db.ForeignKey('division.id'),
            nullable=False)

    #: The division this permission is granting access to
    division = db.relationship('Division',
            back_populates='division_permissions')

    entity_id = db.Column(db.Integer, db.ForeignKey('entity.id'),
            nullable=False)

    #: The :py:class:`Entity` being granted access
    entity = db.relationship(Entity, back_populates='entity_permissions')

    #: The permission being granted.
    permission = db.Column(PermissionType.db_type(), nullable=False)

    def __init__(self, division, permission, entity):
        """Create a Permission object granting an entity access to a division.
        """
        self.division = division
        self.entity = entity
        self.permission = permission

    def __repr__(self):
        return ("{x.__class__.__name__}('{x.permission}', {x.entity}, "
               "{x.division})").format(x=self)


class TransformerRef(db.Model, AutoID, AutoName):
    """Stores associations between :py:class:`~.Transformer`\s and
    :py:class:`.Division`\s.
    """

    __table_args__ = (
        db.UniqueConstraint('division_id', 'attribute_name'),
    )

    #: The attribute this transformer is applied to.
    attribute_name = db.Column(db.String(50), nullable=False)

    #: The transformer instance.
    transformer = db.Column(db.PickleType, nullable=True)

    division_id = db.Column(db.Integer, db.ForeignKey('division.id'),
            nullable=False)

    #: The division the transformer is associated with
    division = db.relationship('Division',
            back_populates='division_transformers')

    @db.validates('transformer')
    def prune_null_transformers(self, attr, transformer):
        """Removes :py:class:`TransformerRef`\s when :py:attr:`.transformer` is
        removed.
        """
        if transformer is None:
            self.division = None
        return transformer


class Division(db.Model, AutoID, AutoName):
    """A reimbursement division.

    A division has (possibly non-intersecting) groups of people that can submit
    requests, review requests, and pay out requests.
    """

    #: The name of this division.
    name = db.Column(db.String(128), nullable=False)

    #: All :py:class:`Permission`\s associated with this division.
    division_permissions = db.relationship(Permission, collection_class=set,
            back_populates='division')

    #: :py:class:`Request` s filed under this division.
    requests = db.relationship(Request, back_populates='division')

    division_transformers = db.relationship(TransformerRef,
            collection_class=attribute_mapped_collection('attribute_name'),
            back_populates='division', cascade='delete,delete-orphan')

    #: A mapping of attribute names to :py:class:`~.transformer.Transformer`
    #: instances.
    transformers = association_proxy(
            'division_transformers',
            'transformer',
            creator=lambda attr, trans:
                    TransformerRef(attribute_name=attr, transformer=trans))

    @property
    def permissions(self):
        """The permissions objects for this division, mapped via their
        permission names.
        """
        class _PermProxy(object):
            def __init__(self, perms):
                self.perms = perms
            def __getitem__(self, key):
                return set(filter(lambda x: x.permission == key, self.perms))
        return _PermProxy(self.division_permissions)

    def __init__(self, name):
        self.name = name

    def __repr__(self):
        return "{x.__class__.__name__}('{x.name}')".format(x=self)

    @db.validates('division_permissions')
    def _invalidate_permission_cache(self, key, value):
        """Invalidates the permissions cache whenever any permissions are
        changed.
        """
        _cached_has_permission.cache_clear()
        return value
