class StoredProcedureException(Exception):
    def __str__(self):
        return unicode(self).encode('ascii', 'replace')

class ProcedureExecutionException(StoredProcedureException):
    def __init__(self, operational_error):
        self.operational_error = operational_error
    
    def __unicode__(self):
        return unicode(self.operational_error)

class ProcedureDoesNotExistException(ProcedureExecutionException):
    pass
    
class IncorrectNumberOfArgumentsException(ProcedureExecutionException):
    def __init__(self, operational_error, arguments):
        self.operational_error = operational_error
        self.arguments = arguments
    
    def __unicode__(self):
        return 'We know of the arguments %s, but upon calling the procedure with these arguments filled in, the error "%s" occurred. Please check whether the argument list is correct.' % \
            (
                    ','.join(self.arguments)
                ,   self.operational_error
            )
    
class ProcedureCreationException(StoredProcedureException):
    def __init__(self, operational_error):
        self.operational_error = operational_error
    
    def __unicode__(self):
        return unicode(self.operational_error)
        
class NameNotKnownException(StoredProcedureException):
    def __init__(self, procedure, exp):
        self.procedure = procedure
        self.exp = exp
    
    def __unicode__(self):
        return 'Unkown key %s in rendering %s' % (self.exp.args[0], self.procedure)

class ProcedureNotParsableException(StoredProcedureException):
    def __unicode__(self):
        return 'The stored procedure could not be parsed'

class ArgumentsIrretrievableException(ProcedureNotParsableException):
    def __unicode__(self):
        return 'The arguments of the stored procedure could not be parsed'

class FileDoesNotWorkException(StoredProcedureException):
    def __init__(self, error):
        self.error = error
    
    def __unicode__(self):
        return 'Unable to open desired file, raised %s' % self.error

class InitializationException(StoredProcedureException):
    def __init__(self, field_name, field_types, value):
        self.field_name = field_name
        self.field_types = field_types
        self.value = value
    
    def __unicode__(self):
        return  'Invalid argument given to initialization of Stored Procedure, %s should have been of type %s, the provided value %s was of type %s' % \
            (
                    self.field_name
                ,   ','.join(map(unicode, self.field_types))
                ,   self.value
                ,   type(self.value)
            )

class InvalidArgument(StoredProcedureException):
    def __init__(self, argument):
        self.argument = argument
    
    def __unicode__(self):
        return 'The argument %s is invalid' % self.argument

class InsufficientArguments(StoredProcedureException):
    def __init__(self, provided_arguments, needed_arguments):
        provided_arguments = frozenset(arg[0] for arg in provided_arguments)
        needed_arguments = frozenset(needed_arguments)
        
        self.omitted = needed_arguments - provided_arguments
    
    def __unicode__(self):
        return 'Insufficient amount of arguments, you omitted to provide %s.' % \
            ','.join(self.omitted)