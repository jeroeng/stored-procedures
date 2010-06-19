from library import library
from django.db.utils import DatabaseError
from django.db import connection

class SQL():
    def __init__(
                self
            ,   content                 # The actual sql code
            ,   yieldResults     = True # Whether a call should yield the results (True) or cursor (False)
            ):
        self._raw_content  = content
        self._yieldResults = yiedResults

    @property
    def content(self):
        if not hasattr(self, '_rendered_content'):
            self._rendered_content = library.replaceNames(
                sql     = self._raw_content
                KeyExp  = None # Write this
            )

        return self._rendered_content

    def __call__(self, *args, **kwargs):
        cursor = connection.cursor()

        try:
            resultCount = cursor.execute(self.content, args)
        except DatabaseError as exp:
            raise RawSQLException(exp)

        if yieldResults:
            results = cursor.fetchall()
            cursor.close()

            return (resultCount, results)
        else:
            return (resultCount, cursor)

    def __unicode__(self):
        return self.content

