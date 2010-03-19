from django.db import models, connection
import re

modelNames = re.compile( r'\[(?P<token>[_\w]+(.[_\w]+)*)\]', re.UNICODE)

def buildNameDict():
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
                nameDictionary[field_prefix % field.attname] = \
                    quote(field.column)
    
    return nameDictionary

nameDictionary = buildNameDict()

def fill_in_names(match):
    global nameDictionary
    
    try:
        value = nameDictionary[match.group('token')]
    except KeyError as exp:
        raise exp
    
    return value
    
def process_custom_sql(procedure):
    return modelNames.sub(fill_in_names, procedure)