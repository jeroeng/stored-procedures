from django.db import connection
from django.template import Template, Context
from django.db.utils import DatabaseError
from django.conf import settings
from _mysql import OperationalError, Warning

import codecs, itertools, re, functools, warnings

from exceptions import *
from library import registerProcedure

IN_OUT_STRING  = '(IN)|(OUT)|(INOUT)'
argumentString = r'(?P<inout>' + IN_OUT_STRING + ')\s*(?P<name>[\w_]+)\s+(?P<type>.+?(?=(,\s*' + IN_OUT_STRING + ')|$))'
argumentParser = re.compile(argumentString, re.DOTALL)

methodParser = re.compile(r'CREATE\s+PROCEDURE\s+(?P<name>[\w_]+)\s*\(\s*(?P<arguments>.*)\)[^\)]*BEGIN', re.DOTALL)

class StoredProcedure():
    def __init__(
                self
            ,   filename
            ,   name            = None
            ,   arguments       = None
            ,   results         = False
            ,   flatten         = True
            ,   context         = None
            ,   raise_warnings  = False
    ):
        """Make a wrapper for a stored procedure

        This provides a wrapper for stored procedures. Given the location of a stored procedure, this wrapper can automatically infer its arguments and name. Consequently, one can call the wrapper as if it were a function, using these arguments as keyword arguments, resulting in calling the stored procedure.

        By default, the stored procedure will be stored in the database (replacing any stored procedure with the same name) on a django-south migrate event.

        It is possible to refer to models and columns of models from within the stored procedure in the following sense. If in the application "shop" one has a model named "Stock", then writing [shop.Stock] in the file describing the stored procedure will yield a the database-name of the model Stock. If this model has a field "shelf", then [shop.Stock.shelf] will yield the field's database name. As a shortcut, one can also use [shop.Stock.pk] to refer to the primary key of Stock. All these names are escaped appropriately.

        Moreover, OperationalError:one can use django templating language in the stored procedure. The argument `context` is fed to this template.

        Keyword arguments:
        filename        -- the file where the stored procedure's content is stored.
        arguments       -- a list of the argument the procedure needs (inferred by default)
        results         -- whether the procedure yields a resultset (default is false)
        flatten         -- whether the resultset, whenever available, should be flattened to its first element, ueful when the procedure only returns one row (default True)
        content         -- a context (dictionary or function which takes the stored procedure itself and yields a dictionary) for rendering the procedure (default is empty)
        raise_warnings  -- whether warnings should be raised as an exception (default is false)"""
        # Save settings
        self._filename = filename
        self._flatten = flatten
        self._raise_warnings = raise_warnings

        self.raw_sql = self.readProcedure()

        # When we are forced to check for the procedures name, this already
        # gives us the argument-data needed to process the arguments, so save
        # this in case we need it later on
        argumentContent = None

        # Determine name of the procedure
        if name is None:
            argumentContent = self._generate_name()
        elif isinstance(name, str):
            self._name = name.decode('utf-8')
        elif isinstance(name, unicode):
            self._name = name
        else:
            raise InitializationException(
                    procedure   = self
                ,   field_name  = 'name'
                ,   field_types = (None, str, unicode)
                ,   field_value = name
            )

        # Determine the procedures arguments
        if arguments is None:
            self._generate_arguments(argumentContent)
        elif isinstance(arguments, list):
           self._generate_shuffle_arguments(arguments)
        else:
            raise InitializationException(
                    procedure   = self
                ,   field_name  = 'arguments'
                ,   field_types = (None, list)
                ,   field_value = arguments
            )

        # Determine whether the procedure should return any results
        if isinstance(results, bool):
            self._hasResults = results
        elif results is None:
            self._hasResults = False
        else:
            raise InitializationException(
                    procedure   = self
                ,   field_name  = 'results'
                ,   field_types = (None, bool)
                ,   field_value = results
            )

        # Determine additional context for the rendering of the procedure
        if isinstance(context, dict) or callable(context):
            self._context = context
        elif context is None:
            self._context = None
        else:
            raise InitializationException(
                    procedure   = self
                ,   field_name  = 'context'
                ,   field_types = (None, dict, 'function')
                ,   field_value = context
            )

        # Register the procedure
        registerProcedure(self)

    def readProcedure(self):
        """Read the procedure from the given location. The procedure is assumed to be stored in utf-8 encoding."""
        if hasattr(settings, 'IN_SITE_ROOT'):
        	name = settings.IN_SITE_ROOT(self.filename)
        else:
        	name = self.filename

        try:
            fileHandler = codecs.open(name, 'r', 'utf-8')
        except IOError as exp:
            raise FileDoesNotWorkException(
                procedure  = self,
                file_error = exp
            )

        return fileHandler.read()

    def resetProcedure(self, library, verbosity = 2):
        # Determine context of the procedure
        renderContext = \
            {
                    'name'      :   connection.ops.quote_name(self.name)
            }

        # Fill in global context
        if not self._context is None:
            # fetch the context
            if callable(self._context):
                try:
                    context = self._context(self)
                except Exception as exp:
                    raise ProcedureContextException(
                            procedure = self
                        ,   exp       = exp
                    )
            else:
                context = self._context

            renderContext.update(context)

        # Render SQL
        sqlTemplate = Template(self.raw_sql)
        preprocessed_sql = sqlTemplate.render(Context(renderContext))

        # Fill in actual names
        self.sql = library.replaceNames(
                self.raw_sql
            ,   functools.partial(ProcedureKeyException, procedure = self)
        )

        # Store the procedure in the database
        self.send_to_database(verbosity)

    def send_to_database(self, verbosity):
        cursor = connection.cursor()

        # Try to delete the procedure, if it exists
        try:
            # The database may give a warning when deleting a stored procedure which does not already
            # exist. This warning is worthless
            with warnings.catch_warnings(record = True) as ws:
                # When sufficiently verbose or pedantic, display warnings
                warnings.simplefilter('always' if verbosity >= 2 or self._raise_warnings else 'ignore')

                cursor.execute('DROP PROCEDURE IF EXISTS %s' % connection.ops.quote_name(self.name))
                cursor.execute(self.sql)

                if len(ws) >= 1:
                    print "Warning during creation of %s" % self

                    for warning in ws:
                        print '\t%s' % warning.message

        except (DatabaseError, OperationalError) as exp:
            raise ProcedureCreationException(
                    procedure         = self
                ,   operational_error = exp
            )

        cursor.close()

    def __call__(self, *args, **kwargs):
        """Call the stored procedure. Arguments and keyword arguments to this method are fed to the stored procedure. First, all arguments are used, and then the keyword arguments are filled in. Nameclashes result in a TypeError."""
        # Fetch the procedures arguments
        for arg, value in itertools.izip(self.arguments, args):
            if arg in kwargs:
                raise TypeError('Argument at %s clashes, given via *args and **kwargs' % arg)

            kwargs[arg] = value

        args = list(self._shuffle_arguments(kwargs))

        cursor = connection.cursor()

        try:
            cursor.execute(self.call, args)
        except (DatabaseError, OperationalError) as exp:
            # Something went wrong, find out what
            code, message = exp.args
            if code == 1305:
                # Procedure does not exist
                raise ProcedureDoesNotExistException(
                        procedure         = self
                    ,   operational_error = exp
                )
            elif code == 1318:
                # Incorrect number of argument, the argument list must be incorrect
                raise IncorrectNumberOfArgumentsException(
                        procedure          = self
                    ,   operational_error  = exp
                )
            else:
                # Some other error occurred
                raise ProcedureExecutionException(
                        procedure         = self
                    ,   operational_error = exp
                )

        # Always force the cursor to free its warnings
        with warnings.catch_warnings(record = True) as ws:
            warnings.simplefilter('always' if self._raise_warnings else 'ignore')

            if self.hasResults:
                # There are some results to be fetched
                results = cursor.fetchall()

            cursor.close()

            if len(ws) >= 1:
                # A warning was raised, raise it whenever the user wants
                raise ProcedureExecutionWarnings(
                        procedure   = self
                    ,   warnings    = ws
                )

        if self.hasResults:
            # if so requested, return only the first set of results
            return results[0] if self._flatten else results

    # Properties
    name = property(
                fget = lambda self: self._name
            ,   doc  = 'Name of the stored procedure'
        )

    filename = property(
                fget = lambda self: self._filename
            ,   doc  = 'Filename of the stored procedure'
        )

    arguments = property(
                fget = lambda self: self._arguments
            ,   doc  = 'Arguments the procedure accepts'
        )

    hasResults = property(
                fget = lambda self: self._hasResults
            ,   doc  = 'Whether the stored procedures requires a fetch after execution'
        )

    call       = property(
                fget  = lambda self: self._call
            ,   doc   = 'The SQL code needed to call this stored procedure'
    )

    def _match_procedure(self):
        match = methodParser.match(self.raw_sql)

        if match is None:
            raise ProcedureNotParsableException(
                procedure = self
            )

        return match

    def _generate_name(self):
        match = self._match_procedure()

        self._name = match.group('name')

        return match.group('arguments')

    def _generate_arguments(self, argumentContent):
        # When the list of arguments is not given, we retrieve it from the procedure
        if argumentContent is None:
            argumentContent = self._match_procedure().group('arguments')

        argumentData = []

        for match in argumentParser.finditer(argumentContent):
            name  = match.group('name')
            type  = match.group('type')
            inout = match.group('inout')

            argumentData.append((name, type, inout))

        self._generate_shuffle_arguments(argumentData)

    def _generate_shuffle_arguments(self, arguments):
        """Generate a method for shuffling a dictionary whose keys match exactly the contents of arguments into the order as given by arguments."""
        # First set the help of the call-method
        self._arguments = [ name for (name, _, _) in arguments ]
        argCount = len(arguments)

        # Generate the SQL needed to call the procedure
        self._generate_call(argCount)

        # Generate the function which shuffles the arguments into the appropriate
        # order on each stored procedure call
        def shuffle_argument(argValues):
            """Meant for internal use only, shuffles the arguments into correct order"""
            argumentValues = []

            for (argName, argType, argInOut) in arguments:
                # Try to grab the argument
                try:
                    value = argValues.pop(argName)
                except KeyError:
                    continue

                argumentValues.append(value)

            # Notify the user of invalid arguments
            if len(argValues) > 0:
                raise InvalidArgument(
                            procedure = self
                        ,   arguments = argValues.keys()
                    )

            # Notify the user of missing arguments
            if len(argumentValues) < argCount:
                raise InsufficientArguments(
                        procedure          = self
                    ,   provided_arguments = argValues.keys()
                )

            return argumentValues

        self._shuffle_arguments = shuffle_argument

    def _generate_call(self, argCount):
        """Generates the call to this procedure"""
        self._call = 'CALL %s (%s)' % \
            (
                    connection.ops.quote_name(self.name)
                ,   ','.join('%s' for _ in xrange(0, argCount))
            )

    def __unicode__(self):
        return u'%s (%s)' % (self.name, self.filename)

    def __str__(self):
        return unicode(self).encode('ascii', 'replace')

