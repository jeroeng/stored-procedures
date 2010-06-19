from library import library

try:
    from django.db.utils import DatabaseError
    from django.db import connection
except Exception as exp:
    print exp

from _mysql import OperationalError
import warnings

from exceptions import *

class SQL():
    def __init__(
                self
            ,   content
            ,   yield_results = True
            ,   raise_warnings  = False
            ):
        """Wrapper for raw SQL statements.

This allows one to wrap raw SQL code, with the same name-reference system as in :class:`procedure.StoredProcedure`.

:param content: The actual raw SQL.
:type content: `string`
:param yield_results: Whether a call should yield the results (`True`) or cursor (`False`) (default is `True`)
:type yield_results: `bool`
:param raise_warnings: Whether warnings should be raised as an `Exception`, in the case that `yield_results` is set to `True` (default if `False`)
:type raise_warnings: `bool`
"""
        self._raw_content  = content
        self._yield_results = yield_results

    @property
    def content(self):
        if not hasattr(self, '_rendered_content'):
            self._rendered_content = library.replaceNames(
                    sql     = self._raw_content
                ,   KeyExp  = RawSQLKeyException
            )

        return self._rendered_content

    def __call__(self, *args, **kwargs):
        """Execute the SQL query"""
        cursor = connection.cursor()

        try:
            resultCount = cursor.execute(self.content, args)
        except (DatabaseError, OperationalError) as exp:
            raise RawSQLException(exp)

        if self._yield_results:
            with warnings.catch_warnings(record = True) as ws:
                warnings.simplefilter('always' if self._raise_warnings else 'ignore')

                results = cursor.fetchall()
                cursor.close()

                if len(ws) >= 1:
                    raise RawSQLWarning(warnings = ws)

            return (resultCount, results)
        else:
            return (resultCount, cursor)

    def __unicode__(self):
        return self.content

    def __str__(self):
        return unicode(self).encode('utf8', 'replace')

