from django.db import connection
from django.template import Template, Context
from django.db.utils import DatabaseError

from _mysql import OperationalError, Warning

import codecs, itertools, re, functools

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
            ,   raise_warnings  = True
            ,   context         = None
    ):
        # Save settings
        self._filename = filename
        self._raise_warnings = raise_warnings
        self._flatten = flatten

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
        if isinstance(context, dict):
            self._context = context
        elif context is None:
            self._context = None
        else:
            raise InitializationException(
                    procedure   = self
                ,   field_name  = 'context'
                ,   field_types = (None, dict)
                ,   field_value = context
            )

        # Register the procedure
        registerProcedure(self)

    def readProcedure(self):
        """Read the procedure from the given location. The procedure is assumed
        to be stored in utf-8 encoding."""
        try:
            fileHandler = codecs.open(self.filename, 'r', 'utf-8')
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
            renderContext.update(self._context)

        # Render SQL
        sqlTemplate = Template(self.raw_sql)
        preprocessed_sql = sqlTemplate.render(Context(renderContext))

        # Fill in actual names
        self.sql = library.replaceNames(
                self.raw_sql
            ,   functools.partial(ProcedurePreparationException, procedure = self)
        )

        # Store the procedure in the database
        self.send_to_database(verbosity)

    def send_to_database(self, verbosity):
        cursor = connection.cursor()

        # Try to delete the procedure, if it exists
        try:
            cursor.execute('DROP PROCEDURE IF EXISTS %s' % connection.ops.quote_name(self.name))
        except DatabaseError as exp:
            raise ProcedureCreationException(
                    procedure         = self
                ,   operational_error = exp
            )
        except OperationalError as exp:
            raise ProcedureCreationException(
                    procedure         = self
                ,   operational_error = exp
            )
        except Warning as exp:
            # Warnings do not really matter
            if verbosity >= 2:
                print 'Warning raising while deleting stored procedure %s(%s):\n\t%s' %\
                    (self.name, self.filename, exp)

        # Try to insert the procedure
        try:
            cursor.execute(self.sql)
        except DatabaseError as exp:
            raise ProcedureCreationException(
                    procedure         = self
                ,   operational_error = exp
            )
        except OperationalError as exp:
            raise ProcedureCreationException(
                    procedure         = self
                ,   operational_error = exp
            )
        except Warning as exp:
            # Warnings do not really matter
            if verbosity >= 2:
                print 'Warning raising while creating stored procedure %s(%s):\n\t%s' %\
                    (self.name, self.filename, exp)

        cursor.close()

    def __call__(self, *args, **kwargs):
        for arg, value in itertools.izip(self.arguments, args):
            if arg in kwargs:
                raise TypeError('Argument at %s clashes, given via *args and **kwargs' % arg)

            kwargs[arg] = value

        args = self._shuffle_arguments(kwargs)

        # Todo, wrap try-catch around this
        cursor = connection.cursor()
        executed = True
        try:
            cursor.execute('CALL %s (%s)' % \
                    (
                            connection.ops.quote_name(self.name)
                        ,   ','.join('%s' for _ in xrange(0, self.argCount))
                    )
                ,   list(args)
                )
        except DatabaseError as exp:
            executed = False
        except OperationalError as exp:
            executed = False
        except Warning as warning:
            # A warning was raised, raise it whenever the user wants
            if self._raise_warnings:
                raise ProcedureExecutionException(
                        procedure         = self
                    ,   operational_error = warning
                )

        if not executed:
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

        if self.hasResults:
            # There are some results to be fetched
            results = cursor.fetchall()

            # if so requested, return only the first set of results
            if self._flatten:
                return results[0]

            return results

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
        arguments = []

        for match in argumentParser.finditer(argumentContent):
            name  = match.group('name')
            type  = match.group('type')
            inout = match.group('inout')

            argumentData.append((name, (type, inout)))
            arguments.append(name)

        self._generate_shuffle_arguments(arguments)

    def _generate_shuffle_arguments(self, arguments):
        """Generate a method for shuffling a dictionary whose keys match exactly
        the contents of arguments into the order as given by arguments."""
        # First set the help of the call-method
        self._arguments = arguments

        decoratedArguments = dict(itertools.izip(arguments, itertools.count(0)))
        self.argCount = argCount = len(arguments)

        def key(arg_value_pair):
            arg, value = arg_value_pair

            try:
                pos = decoratedArguments[arg]
            except KeyError:
                raise InvalidArgument(
                        procedure = self
                    ,   argument  = arg
                )

            return pos

        def shuffle_argument(argValues):
            """Meant for internal use only, shuffles the arguments into correct order"""
            shuffled = sorted(argValues.iteritems(), key = key)

            if len(shuffled) < argCount:
                raise InsufficientArguments(
                        procedure          = self
                    ,   provided_arguments = argValues.keys()
                )

            return (value for _, value in shuffled)

        self._shuffle_arguments = shuffle_argument

    def __unicode__(self):
        return u'%s (%s)' % (self.name, self.filename)

    def __str__(self):
        return unicode(self).encode('ascii', 'replace')

