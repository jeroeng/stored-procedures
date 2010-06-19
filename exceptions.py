try:
    from django.core.exceptions import ImproperlyConfigured
except Exception as exp:
    print exp

from _mysql import OperationalError, Warning

class StoredProcedureException(Exception):
    """Generic exception related to a stored procedure."""
    def __init__(self, procedure):
        self._procedure = procedure

    procedure = property(lambda self: self._procedure)

    def _description(self):
        """"Subclasses should override this method to provide a more detailled
        _description of the exception that occurred."""
        return None

    def __unicode__(self):
        """Provided a nice _description of the exception."""
        try:
            _description = self._description()
        except Exception as exp:
            _description = '[Error not properly rendered due to %s]' % exp

        return 'Exception in stored procedure %s' % self.procedure + (
            '' if _description is None else ': ' + _description)

    def __str__(self):
        return unicode(self).encode('utf8', 'replace')

class ProcedureExecutionException(StoredProcedureException):
    """Exception that occurs during the execution of a stored procedure."""
    def __init__(self, **kwargs):
        """The argument `operational_error` is required, this should contain an OperationalError."""
        self.operational_error = kwargs.pop('operational_error')
        super(ProcedureExecutionException, self).__init__(**kwargs)

    def _description(self):
        return unicode(self.operational_error)

class ProcedureExecutionWarnings(ProcedureExecutionException):
    """Exception that occurs during the execution of a stored procedure."""
    def __init__(self, **kwargs):
        """The argument `warnings` is required, this should instances of Warning."""
        self.operational_error = kwargs.pop('warnings')
        super(ProcedureExecutionException, self).__init__(**kwargs)

    def _description(self):
        return ', '.join(unicode(warning.message) for warning in self.operational_error)

class ProcedureDoesNotExistException(ProcedureExecutionException):
    def _description(self):
        return 'The database does not know this procedure and gave the exception "%s". Perhaps you forgot to store it in the database?' % self.operational_error

class IncorrectNumberOfArgumentsException(ProcedureExecutionException):
    def _description(self):
        return 'We know of the arguments %s, but upon calling the procedure with these arguments filled in, the error "%s" occurred. Please check whether the argument list is correct.' % \
            (
                    ','.join(self.procedure.arguments)
                ,   self.operational_error
            )

class ProcedurePreparationException(StoredProcedureException):
    pass

class ProcedureContextException(ProcedurePreparationException):
    def __init__(self, **kwargs):
        """The argument `exp` is required, contains the exception raised by the context-creation function"""
        self.exp = kwargs.pop('exp')
        super(ProcedureContextException, self).__init__(**kwargs)

    def _description(self):
        return 'In processing the context, the exception "%s" occurred' % self.exp

class ProcedureKeyException(ProcedurePreparationException):
    def __init__(self, **kwargs):
        """The argument `key` is required, contains the key which could not be found."""
        self.key = kwargs.pop('key')
        super(ProcedureKeyException, self).__init__(**kwargs)

    def _description(self):
        return 'Key "%s" could not be found in processing the procedure\'s contents.' % self.key

class ProcedureCreationException(StoredProcedureException):
    """Exception that occurs during the creation of a stored procedure."""
    def __init__(self, **kwargs):
        """The argument `operational_error` is required, this should contain
        an OperationalError."""
        self.operational_error = kwargs.pop('operational_error')
        super(ProcedureCreationException, self).__init__(**kwargs)

    def _description(self):
        return unicode(self.operational_error)

class ProcedureConfigurationException(StoredProcedureException, ImproperlyConfigured):
    """Exception that occurs during the initialization of a stored procedure.
    Exceptions of this type are also ImproperlyConfigured exceptions, as django
    should flat out stop when they occur."""

class ProcedureNotParsableException(ProcedureConfigurationException):
    def _description(self):
        return 'The stored procedure could not be parsed'

class ArgumentsIrretrievableException(ProcedureNotParsableException):
    def _description(self):
        return super(ArgumentsIrretrievableException, self) + \
            '; its could not be parsed.'

class FileDoesNotWorkException(ProcedureConfigurationException):
    def __init__(self, **kwargs):
        self.file_error = kwargs.pop('file_error')
        super(FileDoesNotWorkException, self).__init__(**kwargs)

    def _description(self):
        return 'Unable to open desired file, raised %s' % self.file_error

class InitializationException(StoredProcedureException):
    """One of the arguments of the stored procedure's constructor was incorrect."""
    def __init__(self, **kwargs):
        self.field_name  = kwargs.pop('field_name')
        self.field_types = kwargs.pop('field_types')
        self.value       = kwargs.pop('value')
        super(InitializationException, self).__init__(**kwargs)

    def _description(self):
        return  'Invalid argument given to initialization, %s should have been of type %s, the provided value %s was of type %s' % \
            (
                    self.field_name
                ,   ','.join(map(unicode, self.field_types))
                ,   self.value
                ,   type(self.value)
            )

class InvalidArgument(StoredProcedureException):
    def __init__(self, **kwargs):
        self.arguments = kwargs.pop('arguments')
        self.given     = kwargs.pop('given')
        super(InvalidArgument, self).__init__(**kwargs)

    def _description(self):
        # Notify the user about which of the provided arguments were wrong,
        # and which ones he could have used.
        return 'This procedure only takes the arguments %(expected)s, you provided: %(rejected)s' % \
            {
                    'expected' : ', '.join(set(self.procedure.arguments) - self.given)
                ,   'rejected' : ', '.join(self.arguments)
            }

class InsufficientArguments(StoredProcedureException):
    def __init__(self, **kwargs):
        provided_arguments = frozenset(kwargs.pop('provided_arguments'))
        super(InsufficientArguments, self).__init__(**kwargs)
        self.omitted = frozenset(self.procedure.arguments) - provided_arguments

    def _description(self):
        return 'Insufficient amount of arguments, you omitted to provide %s.' % \
            ','.join(self.omitted)

class RawSQLException(Exception):
    """Generic exception related to raw sql"""
    def __str__(self):
        return unicode(self).encode('utf8', 'replace')

class RawSQLKeyException(RawSQLException):
    def __init__(self, key):
        self.key = key

    def __unicode__(self):
        return 'Could not find key %s' % self.key

class RawSQLWarning(RawSQLException):
    def __init__(self, warnings):
        self.warnings = warnings

    def __unicode__(self):
        return 'Warning: %s' % \
            ', '.join(unicode(warning.message) for warning in self.warnings)

