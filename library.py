try:
    from django.db.models.signals import post_syncdb
    from django.db import models, connection
except Exception as exp:
    print exp

import re

class StoredProcedureLibary():
    def __init__(self):
        self._procedures = []
        self._reset = False
        self._modelLibrary = None
        self._nameRegexp = re.compile( r'\[(?P<token>[_\w]+(.[_\w]+)*)\]', re.UNICODE)

    def buildModelLibrary(self):
        nameDictionary = dict()
        quote = connection.ops.quote_name

        for app in models.get_apps():
            app_name         = app.__name__.split('.')[-2]
            app_prefix       = '%s.%%s' % app_name
            app_field_prefix = '%s.%%s.%%%%s' % app_name

            for model in models.get_models(app, include_auto_created=True):
                model_prefix = app_prefix % model.__name__
                field_prefix = app_field_prefix % model.__name__

                meta = model._meta

                nameDictionary[model_prefix] = meta.db_table
                nameDictionary[field_prefix % 'pk'] = meta.pk.column

                for field in meta.fields:
                    nameDictionary[field_prefix % field.name] = \
                        quote(field.column)

        return nameDictionary

    def replaceNames(self, sql, KeyExp):
        nameDict = self.modelLibrary

        def fill_in_names(match):
            try:
                value = nameDict[match.group('token')]
            except KeyError as exp:
                raise KeyExp(key = exp.args[0])

            return value

        return self._nameRegexp.sub(fill_in_names, sql)

    def registerProcedure(self, procedure):
        """Each stored procedure is registered with the library."""
        self._procedures.append(procedure)

    def resetProcedures(self, verbosity, force_repeat = False):
        if self._reset and not force_repeat:
            return

        self._reset = True

        for procedure in self.procedures:
            procedure.resetProcedure(
                    verbosity   = verbosity
                ,   library     = self
            )

    procedures = property(
            fget = lambda self: self._procedures
        ,   doc  = 'List of all stored procedures registered at the library'
    )

    @property
    def modelLibrary(self):
        if self._modelLibrary is None:
            self._modelLibrary = self.buildModelLibrary()

        return self._modelLibrary

library = StoredProcedureLibary()

def registerProcedure(procedure):
    """Registers a procedure with the libary."""
    library.registerProcedure(procedure)

def resetProcedures(verbosity = 2):
    """Resets all procedures registered with the library in the database."""
    library.resetProcedures(verbosity)

def reset(sender, **kwargs):
    resetProcedures(1)

# Connect to syncdb
# post_syncdb.connect(reset)

# Connect to south's handler
try:
    from south.signals import post_migrate

    post_migrate.connect(reset)
except ImportError:
    pass

