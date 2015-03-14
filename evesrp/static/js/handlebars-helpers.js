Handlebars.registerHelper('csrf', function() {
  return $("meta[name='csrf_token']").attr("content");
});

Handlebars.registerHelper('capitalize', function(str) {
  return EveSRP.util.capitalize(str);
});

Handlebars.registerHelper('datefmt', function(date) {
  if (typeof date === 'string') {
    date = new Date(date);
  }
  return [EveSRP.util.padNum(date.getUTCDate(), 2),
          EveSRP.util.monthAbbr(date.getUTCMonth()),
          date.getUTCFullYear()].join(' ');
});

Handlebars.registerHelper('timefmt', function(date) {
  if (typeof date === 'string') {
    date = new Date(date);
  }
  return [EveSRP.util.padNum(date.getUTCHours(), 2),
          EveSRP.util.padNum(date.getUTCMinutes(), 2)].join(':');
});


Handlebars.registerHelper('status_color', function(stat) {
  return EveSRP.util.statusColor(stat);
});

Handlebars.registerHelper('compare', function(left, right, options) {
  var op = options.hash.operator || "===";
  var ops = {
    '==': function(l, r) { return l == r;},
    '!=': function(l, r) { return l != r;},
    '===': function(l, r) { return l === r;},
    '!==': function(l, r) { return l !== r;},
    '<': function(l, r) { return l < r;},
    '>': function(l, r) { return l > r;},
    '<=': function(l, r) { return l <= r;},
    '>=': function(l, r) { return l >= r;},
    'in': function(l, r) { return l in r;}
  };
  var result = ops[op](left, right);
  if (result) {
    return options.fn(this);
  } else {
    return options.inverse(this);
  }
});

Handlebars.registerHelper('count', function(collection) {
  return collection.length;
});

Handlebars.registerHelper('transformed', function(request, attr) {
  if (_.has(request.transformed, attr)) {
    return new Handlebars.SafeString('<a href="' + request.transformed[attr] +
                                     '" target="_blank">' + request[attr] +
                                     ' <i class="fa fa-external-link"></i></a>');
  }
  return request[attr];
});

Handlebars.registerHelper('template', function(templateName) {
  var template = Handlebars.templates[templateName],
      output = template(this);
  return new Handlebars.SafeString(output);
});
