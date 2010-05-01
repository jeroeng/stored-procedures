from django.core.exceptions import ImproperlyConfigured
from _mysql import OperationalError, Warning

class StoredProcedureException(Exception):
    """Generic exception related to a stored procedure."""
    def __init__(self, procedure):
        self._procedure = procedure

    procedure = property(lambda self: self._procedure)

    def description(self):
        """"Subclasses should override this method to provide a more detailled
        description of the exception that occurred."""
        return None

    def __unicode__(self):
        description = self.description()

        return 'Exception in stored procedure %s' % self.procedure + (
            '' if description is None else ': ' + description)

    def __str__(self):
        return unicode(self)

class ProcedureExecutionException(StoredProcedureException):
    """Exception that occurs during the execution of a stored procedure."""
    def __init__(self, **kwargs):
        """The argument `operational_error` is required, this should contain
        an OperationalError."""
        self.operational_error = kwargs.pop('operational_error')
        super(ProcedureExecutionException, self).__init__(**kwargs)

    def description(self):
        return unicode(self.operational_error)

class ProcedureDoesNotExistException(ProcedureExecutionException):
    pass

class IncorrectNumberOfArgumentsException(ProcedureExecutionException):
    def description(self):
        return 'We know of the arguments %s, but upon calling the procedure with these arguments filled in, the error "%s" occurred. Please check whether the argument list is correct.' % \
            (
                    ','.join(self.procedure.arguments)
                ,   self.operational_error
            )

class ProcedurePreparationException(StoredProcedureException):
    def __init__(self, **kwargs):
        """The argument `key` is required, contains the key which could
        not be found."""
        self.key = kwargs.pop('key')
        super(ProcedurePreparationException, self).__init__(**kwargs)

    def description(self):
        return u'Key "%s" could not be found' % self.key

class ProcedureCreationException(StoredProcedureException):
    """Exception that occurs during the creation of a stored procedure."""
    def __init__(self, **kwargs):
        """The argument `operational_error` is required, this should contain
        an OperationalError."""
        self.operational_error = kwargs.pop('operational_error')
        super(ProcedureCreationException, self).__init__(**kwargs)

    def description(self):
        return unicode(self.operational_error)

class ProcedureConfigurationException(StoredProcedureException, ImproperlyConfigured):
    """Exception that occurs during the initialization of a stored procedure.
    Exceptions of this type are also ImproperlyConfigured exceptions, as django
    should flat out stop when they occur."""

class ProcedureNotParsableException(ProcedureConfigurationException):
    def description(self):
        return 'The stored procedure could not be parsed'

class ArgumentsIrretrievableException(ProcedureNotParsableException):
    def description(self):
        return super(ArgumentsIrretrievableException, self) + \
            '; its could not be parsed.'

class FileDoesNotWorkException(ProcedureConfigurationException):
    def __init__(self, **kwargs):
        self.file_error = kwargs.pop('file_error')
        super(FileDoesNotWorkException, self).__init__(**kwargs)

    def description(self):
        return 'Unable to open desired file, raised %s' % self.file_error

class InitializationException(StoredProcedureException):
    """One of the arguments of the stored procedure's constructor was incorrect."""
    def __init__(self, **kwargs):
        self.field_name  = kwargs.pop('field_name')
        self.field_types = kwargs.pop('field_types')
        self.value       = kwargs.pop('value')
        super(InitializationException, self).__init__(**kwargs)

    def description(self):
        return  'Invalid argument given to initialization, %s should have been of type %s, the provided value %s was of type %s' % \
            (
                    self.field_name
                ,   ','.join(map(unicode, self.field_types))
                ,   self.value
                ,   type(self.value)
            )

class InvalidArgument(StoredProcedureException):
    def __init__(self, **kwargs):
        self.argument = kwargs.pop('argument')

    def description(self):
        return 'The argument %s is was not expected. Perhaps you meant one of %s?' % \
            (
                    self.argument
                ,   ','.join(self.procedure.arguments)
            )

class InsufficientArguments(StoredProcedureException):
    def __init__(self, **kwargs):
        provided_arguments = frozenset(arg[0] for arg in kwargs.pop('provided_arguments'))
        super(InsufficientArguments, self).__init__(**kwargs)
        self.omitted = frozenset(self.procedure.arguments) - provided_arguments

    def description(self):
        return 'Insufficient amount of arguments, you omitted to provide %s.' % \
            ','.join(self.omitted)

