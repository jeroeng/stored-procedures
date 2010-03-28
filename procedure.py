from django.db import connection
from django.template import Template, Context
from django.db.models.signals import post_syncdb

from _mysql import OperationalError, Warning

import codecs, itertools, re, functools

from exceptions import *

IN_OUT_STRING  = '(IN)|(OUT)|(INOUT)'
argumentString = r'(?P<inout>' + IN_OUT_STRING + ')\s*(?P<name>[\w_]+)\s+(?P<type>.+?(?=(,\s*' + IN_OUT_STRING + ')|$))'
argumentParser = re.compile(argumentString, re.DOTALL)

methodParser = re.compile(r'CREATE\s+PROCEDURE\s+(?P<name>[\w_]+)\s*\(\s*(?P<arguments>.*)\)[^\)]*BEGIN', re.DOTALL) 

class StoredProcedure():
    def __init__(self, filename, name = None, arguments = None, results = False, flatten = True, raise_warnings = True):
        self.raw_sql = self.readProcedure(filename)
        
        self._raise_warnings = raise_warnings
        self._flatten = flatten
        argumentContent = None
        
        if name is None:
            argumentContent = self._generate_name()
        elif isinstance(name, str):
            self._name = name.decode('utf-8')
        elif isinstance(name, unicode):
            self._name = name
        else:
            raise InitializationException('name', (None, str, unicode), name) 

        if arguments is None:
            self._generate_arguments(argumentContent)
        elif isinstance(arguments, list):
           self._generate_shuffle_arguments(arguments)
        else:
            raise InitializationException('arguments', (None, list), arguments)
            
        if isinstance(results, bool):
            self._hasResults = results
        elif results is None:
            self._hasResults = False
        else:
            raise InitializationException('results', (None, bool), results)

        # Connect to syncdb
        self._hasSynced = False
        post_syncdb.connect(self.postsync)
        
    def readProcedure(self, filename):
        try:
            fileHandler = codecs.open(filename, 'r', 'utf-8')
        except IOError as exp:
            raise FileDoesNotWorkException(exp)
        
        return fileHandler.read()
        
    def postsync(self, sender, **kwargs):
        # Make sure that this is called only once.
        if self._hasSynced:
            return
        
        verbosity = kwargs['verbosity']
        
        self._hasSynced = True
        
        # Process SQL
        renderContext = \
            {
                    'name'      :   connection.ops.quote_name(self.name)
            }
        self.sql = self.render(renderContext)
        
        self.send_to_database(verbosity)
    
    def send_to_database(self, verbosity):
        cursor = connection.cursor()
        
        # Try to delete the procedure, if it exists
        try:
            cursor.execute('DROP PROCEDURE IF EXISTS %s' % connection.ops.quote_name(self.name))
        except OperationalError as exp:
            raise ProcedureCreationException(exp)
        except Warning as exp:
            # Warnings do not really matter
            if verbosity >= 2:
                print 'Warning raising while deleting stored procedure %s:\n\t%s' %\
                    (self.name, exp)
        
        # Try to insert the procedure
        try:
            cursor.execute(self.sql)
        except OperationalError as exp:
            raise ProcedureCreationException(exp)
        except Warning as exp:
            # Warnings do not really matter
            if verbosity >= 2:
                print 'Warning raising while creating stored procedure %s:\n\t%s' %\
                    (self.name, exp)
        
        cursor.close()
        
    def __call__(self, *args, **kwargs):
        for arg, value in itertools.izip(self.arguments, args):
            if arg in kwargs:
                raise TypeError('Argument at %s clashes, given via *args and **kwargs' % arg)
            
            kwargs[arg] = value
    
        args = self._shuffle_arguments(kwargs)
    
        # Todo, wrap try-catch around this
        cursor = connection.cursor()
        try:
            cursor.execute('CALL %s (%s)' % \
                    (
                            connection.ops.quote_name(self.name)
                        ,   ','.join('%s' for _ in xrange(0, self.argCount))
                    )
                ,   list(args)
                )
        except OperationalError as exp:
            # Something went wrong, find out what
            code, message = exp.args
            if code == 1305:
                # Procedure does not exist
                raise ProcedureDoesNotExistException(exp)
            elif code == 1318:
                # Incorrect number of argument, the argument list must be incorrect
                raise IncorrectNumberOfArgumentsException(exp, self.arguments)
            else:
                # Some other error occurred
                raise ProcedureExecutionException(exp)
        except Warning as exp:
            # A warning was raised, raise it whenever the user wants
            if self._raise_warnings:
                raise ProcedureExecutionException(exp)
        
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
    
    arguments = property(
                fget = lambda self: self._arguments
            ,   doc  = 'Arguments the procedure accepts'
        )

    hasResults = property(
                fget = lambda self: self._hasResults
            ,   doc  = 'Whether the stored procedures requires a fetch after execution'
        )
        
    def render(self, renderContext):
        """Render the SQL as provided with variabled into true SQL"""
        from context import process_custom_sql

        sqlTemplate = Template(self.raw_sql)
        preprocessed_sql = sqlTemplate.render(Context(renderContext))
        
        try:
            return process_custom_sql(preprocessed_sql)
        except KeyError as exp:
            raise NameNotKnownException(procedure = self, exp = exp)
    
    def _match_procedure(self):
        match = methodParser.match(self.raw_sql)
        
        if match is None:
            raise ProcedureNotParsableException()
        
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
                raise InvalidArgument(arg)
            
            return pos
        
        def shuffle_argument(argValues):
            """Meant for internal use only, shuffles the arguments into correct order"""
            shuffled = sorted(argValues.iteritems(), key = key)
            
            if len(shuffled) < argCount:
                raise InsufficientArguments(argValues, arguments)
            
            return (value for _, value in shuffled)
        
        self._shuffle_arguments = shuffle_argument
    
    def __unicode__(self):
        return unicode(self.name)