from library import library
from django.db.utils import DatabaseError
from django.db import connection

from exceptions import *

class SQL():
    def __init__(
                self
            ,   content
            ,   yieldResults     = True
            ):
        """Wrapper for raw SQL statements.

        This allows one to wrap raw SQL code, with the same name-reference system as in StoredProcedure.

        Keyword arguments:
            content         -- the actual raw SQL
            yieldResults    -- Whether a call should yield the results (True) or cursor (False) (default is true)"""
        self._raw_content  = content
        self._yieldResults = yieldResults

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
        except DatabaseError as exp:
            raise RawSQLException(exp)

        if self._yieldResults:
            results = cursor.fetchall()
            cursor.close()

            return (resultCount, results)
        else:
            return (resultCount, cursor)

    def __unicode__(self):
        return self.content

    def __str__(self):
        return unicode(self).encode('utf8', 'replace')

