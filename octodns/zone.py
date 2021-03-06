#
#
#

from __future__ import absolute_import, division, print_function, \
    unicode_literals

from logging import getLogger
import re

from .record import Create, Delete


class SubzoneRecordException(Exception):
    pass


class DuplicateRecordException(Exception):
    pass


def _is_eligible(record):
    # Should this record be considered when computing changes
    # We ignore all top-level NS records
    return record._type != 'NS' or record.name != ''


class Zone(object):
    log = getLogger('Zone')

    def __init__(self, name, sub_zones):
        if not name[-1] == '.':
            raise Exception('Invalid zone name {}, missing ending dot'
                            .format(name))
        # Force everyting to lowercase just to be safe
        self.name = str(name).lower() if name else name
        self.sub_zones = sub_zones
        self.records = set()
        # optional leading . to match empty hostname
        # optional trailing . b/c some sources don't have it on their fqdn
        self._name_re = re.compile('\.?{}?$'.format(name))

        self.log.debug('__init__: zone=%s, sub_zones=%s', self, sub_zones)

    def hostname_from_fqdn(self, fqdn):
        return self._name_re.sub('', fqdn)

    def add_record(self, record):
        name = record.name
        last = name.split('.')[-1]
        if last in self.sub_zones:
            if name != last:
                # it's a record for something under a sub-zone
                raise SubzoneRecordException('Record {} is under a '
                                             'managed subzone'
                                             .format(record.fqdn))
            elif record._type != 'NS':
                # It's a non NS record for exactly a sub-zone
                raise SubzoneRecordException('Record {} a managed sub-zone '
                                             'and not of type NS'
                                             .format(record.fqdn))
        if record in self.records:
            raise DuplicateRecordException('Duplicate record {}, type {}'
                                           .format(record.fqdn, record._type))
        self.records.add(record)

    def changes(self, desired, target):
        self.log.debug('changes: zone=%s, target=%s', self, target)

        # Build up a hash of the desired records, thanks to our special
        # __hash__ and __cmp__ on Record we'll be able to look up records that
        # match name and _type with it
        desired_records = {r: r for r in desired.records}

        changes = []

        # Find diffs & removes
        for record in filter(_is_eligible, self.records):
            try:
                desired_record = desired_records[record]
            except KeyError:
                if not target.supports(record):
                    self.log.debug('changes:  skipping record=%s %s - %s does '
                                   'not support it', record.fqdn, record._type,
                                   target.id)
                    continue
                # record has been removed
                self.log.debug('changes: zone=%s, removed record=%s', self,
                               record)
                changes.append(Delete(record))
            else:
                change = record.changes(desired_record, target)
                if change:
                    self.log.debug('changes: zone=%s, modified\n'
                                   '    existing=%s,\n     desired=%s', self,
                                   record, desired_record)
                    changes.append(change)
                else:
                    self.log.debug('changes: zone=%s, n.c. record=%s', self,
                                   record)

        # Find additions, things that are in desired, but missing in ourselves.
        # This uses set math and our special __hash__ and __cmp__ functions as
        # well
        for record in filter(_is_eligible, desired.records - self.records):
            if not target.supports(record):
                self.log.debug('changes:  skipping record=%s %s - %s does not '
                               'support it', record.fqdn, record._type,
                               target.id)
                continue
            self.log.debug('changes: zone=%s, create record=%s', self, record)
            changes.append(Create(record))

        return changes

    def __repr__(self):
        return 'Zone<{}>'.format(self.name)
