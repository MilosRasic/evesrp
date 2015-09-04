jQuery = require 'jquery'
_ = require 'underscore'


exports.monthAbbr = (monthInt) ->
    switch monthInt
        when 0 then 'Jan'
        when 1 then 'Feb'
        when 2 then 'Mar'
        when 3 then 'Apr'
        when 4 then 'May'
        when 5 then 'Jun'
        when 6 then 'Jul'
        when 7 then 'Aug'
        when 8 then 'Sep'
        when 9 then 'Oct'
        when 10 then 'Nov'
        when 11 then 'Dec'


exports.statusColor = (status) ->
    switch status
        when 'evaluating' then 'warning'
        when 'approved' then 'info'
        when 'paid' then 'success'
        when 'incomplete', 'rejected' then 'danger'
        else ''


exports.pageNumbers = (numPages, currentPage, options) ->
    # Set default options
    options = options ? {}
    leftEdge = options.leftEdge ? 2
    leftCurrent = options.leftCurrent ? 2
    rightCurrent = options.rightCurrent ? 5
    rightEdge = options.rightEdge ? 2

    pages = []
    for page in [1..numPages]
        if page <= leftEdge
            pages.push page
        else if (currentPage - leftCurrent) <= page < (currentPage + rightCurrent)
            pages.push page
        else if numPages - rightEdge < page
            pages.push page
        else if pages[pages.length - 1] != null
            pages.push null
    return pages
