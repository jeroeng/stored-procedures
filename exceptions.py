try:
    from django.core.exceptions import ImproperlyConfigured
except Exception as exp:
    print exp

from _mysql import OperationalError, Warning

class StoredProcedureException(Exception):
    def __init__(self, procedure):
        """Generic exception related to a stored procedure.

Subclasses should override the method :meth:`~stored_procedures.exceptions.StoredProcedureException._description`, which provides a description of the exception that occurred. This approach is taken to provide a uniform message for all exceptions, at least displaying the procedures's name and filename.

:param procedure: The stored procedure which raised this exception.
:type procedure: :class:`~stored_procedures.procedure.StoredProcedure`"""
        self._procedure = procedure

    procedure = property(lambda self: self._procedure)

    def _description(self):
        """"Subclasses should override this method to provide a more detailled description of the exception that occurred."""
        return None

    def __unicode__(self):
        """Provided a nice description of the exception. In case :meth:`~stored_procedures.exceptions.StoredProcedureException._description' raises :exc:`Exception`, this will be displayed instead of a description."""
        try:
            _description = self._description()
        except Exception as exp:
            _description = '[Error not properly rendered due to %s]' % exp

        return 'Exception in stored procedure %s' % self.procedure + (
            '' if _description is None else ': ' + _description)

    def __str__(self):
        return unicode(self).encode('utf8', 'replace')

class ProcedureExecutionException(StoredProcedureException):
    def __init__(self, **kwargs):
        """Exception that occurs during the execution of a stored procedure.

:param operational_error: The exception that occurred, in most cases this will be of type :exc:`django.db.utils.DatabaseError` or `_mysql.OperationalError`.
:type operational_error: :exc:`Exception`"""

        self.operational_error = kwargs.pop('operational_error')
        super(ProcedureExecutionException, self).__init__(**kwargs)

    def _description(self):
        return unicode(self.operational_error)

class ProcedureExecutionWarnings(ProcedureExecutionException):
    def __init__(self, **kwargs):
        """Warnings that occurred during the execution of a stored procedure.

:param warnings: The warnings that occurred, should be a list of :exc:`Warning`."""
        self.operational_error = kwargs.pop('warnings')
        super(ProcedureExecutionException, self).__init__(**kwargs)

    def _description(self):
        return ', '.join(unicode(warning.message) for warning in self.operational_error)

class ProcedureDoesNotExistException(ProcedureExecutionException):
    """Raised when the stored procedure one tries to call does not exist in the database"""
    def _description(self):
        return 'The database does not know this procedure and gave the exception "%s". Perhaps you forgot to store it in the database?' % self.operational_error

class IncorrectNumberOfArgumentsException(ProcedureExecutionException):
    """Raised when the database expected a different amount of arguments than we know of."""
    def _description(self):
        return 'We know of the arguments %s, but upon calling the procedure with these arguments filled in, the error "%s" occurred. Please check whether the argument list is correct.' % \
            (
                    ','.join(self.procedure.arguments)
                ,   self.operational_error
            )

class ProcedurePreparationException(StoredProcedureException):
    """Raised when something went wrong while preparing the stored procedure for being stored in the database"""
    pass

class ProcedureContextException(ProcedurePreparationException):
    def __init__(self, **kwargs):
        """Raised when rendering the dynamic context raised an :exc:`Exception`.

:param exp: the exception raised by the context-creation function"""
        self.exp = kwargs.pop('exp')
        super(ProcedureContextException, self).__init__(**kwargs)

    def _description(self):
        return 'In processing the context, the exception "%s" occurred' % self.exp

class ProcedureKeyException(ProcedurePreparationException):
    def __init__(self, **kwargs):
        """Raised when a certain reference did not exist.

:param key: contains the key which could not be found."""
        self.key = kwargs.pop('key')
        super(ProcedureKeyException, self).__init__(**kwargs)

    def _description(self):
        return 'Key "%s" could not be found in processing the procedure\'s contents.' % self.key

class ProcedureCreationException(StoredProcedureException):
    def __init__(self, **kwargs):
        """Exception that occurs when storing the stored procedure in the database.

:param operational_error: The exception that occurred, in most cases this will be of type :exc:`django.db.utils.DatabaseError` or `_mysql.OperationalError`.
:type operational_error: :exc:`Exception`"""
        self.operational_error = kwargs.pop('operational_error')
        super(ProcedureCreationException, self).__init__(**kwargs)

    def _description(self):
        return unicode(self.operational_error)

class ProcedureConfigurationException(StoredProcedureException, ImproperlyConfigured):
    """Exception that occurs during the initialization of a stored procedure.
    Exceptions of this type are also :exc:`ImproperlyConfigured` exceptions, as django
    should flat out stop when they occur."""

class ProcedureNotParsableException(ProcedureConfigurationException):
    """Raised when the procedure could not be parsed"""
    def _description(self):
        return 'The stored procedure could not be parsed'

class ArgumentsIrretrievableException(ProcedureNotParsableException):
    """Raised when we can not automatically infer the stored procedure's arguments"""
    def _description(self):
        return super(ArgumentsIrretrievableException, self) + \
            '; its could not be parsed.'

class FileDoesNotWorkException(ProcedureConfigurationException):
    def __init__(self, **kwargs):
        """Raised when the file in which the stored procedures should be contained could not be opened.

:param file_error: Exception that occurred when trying to open the file"""
        self.file_error = kwargs.pop('file_error')
        super(FileDoesNotWorkException, self).__init__(**kwargs)

    def _description(self):
        return 'Unable to open desired file, raised %s' % self.file_error

class InitializationException(ProcedureConfigurationException):
    def __init__(self, **kwargs):
        """Raised when one of the arguments of the stored procedure's constructor was incorrect.

:param field_name: The name of the argument which was incorrectly set
:param field_types: List of types (or names thereof) which would have been accepted
:param value: The offending value."""
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
        """"Raised when invalid arguments were given to the stored procedure

:param arguments: The rejected arguments
:param given: All arguments that were provided"""
        self.arguments = kwargs.pop('arguments')
        self.given     = kwargs.pop('given')
        super(InvalidArgument, self).__init__(**kwargs)

    def _description(self):
        # Notify the user about which of the provided arguments were wrong,
        # and which ones he could have used.
        return 'You provided the illegal arguments %(rejected)s, perhaps you meant: %(expected)s' % \
            {
                    'expected' : ', '.join(set(self.procedure.arguments) - self.given)
                ,   'rejected' : ', '.join(self.arguments)
            }

class InsufficientArguments(StoredProcedureException):
    def __init__(self, **kwargs):
        """Raised when an insufficient amount of arguments was provided to the stored procedure.

:param provided_arguments: List of the arguments that were provided"""
        self.provided_arguments = frozenset(kwargs.pop('provided_arguments'))
        super(InsufficientArguments, self).__init__(**kwargs)

    def _description(self):
        return 'Insufficient amount of arguments, you omitted to provide %s.' % \
            ','.join(self.procedure.arguments - self.provided_arguments)

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

