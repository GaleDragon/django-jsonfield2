import itertools, json 

from django.db import models
from django.db.models import LOOKUP_SEP
from django.utils import six
from jsonpath_rw import parse


class Json(object):
    def __init__(self, json_path, value):
        self.json_path = json_path
        self.regex = parse(json_path)
        self.comparison = value


class JSONAwareQuerySet(models.query.QuerySet):
    def __init__(self, json_fields=None, *args, **kwargs):
        if not json_fields:
            json_fields = []
        self.json_fields = json_fields
        super(JSONAwareQuerySet, self).__init__(*args, **kwargs)

    def _filter_or_exclude(self, negate, *args, **kwargs):
        extra_lookups = {}

        for lookup in kwargs:
            if lookup.split(LOOKUP_SEP)[0] in self.json_fields:
                try:
                    lookupval = lookup.split(LOOKUP_SEP)[1]
                except: 
                    continue 
                if lookupval in ["exact", "iexact", "in", "isnull", "contains", "icontains"]:
                    continue 
                extra_lookups[lookup] = kwargs[lookup]

        for key in extra_lookups:
            kwargs.pop(key)

        clone = super(JSONAwareQuerySet, self)._filter_or_exclude(negate, *args, **kwargs)

        if extra_lookups.keys():
            # self.json_lookups = True  
            len(clone)  # Fill the cache

            # Lista de trabajo recorrida reversa para eliminar los no requeridos              
            result_list = list(clone)

            # for item in itertools.product(self, extra_lookups.keys()):
            for i in range(len(result_list) - 1, -1, -1):
                item = result_list[i]
                for lookupkey in extra_lookups.keys():
                    evalresult = self._evaluate_json_lookup(item, lookupkey, extra_lookups[lookupkey])
                    if negate:
                        evalresult = not evalresult
                    if not evalresult:
                        result_list.pop(i)
                        break

            clone._result_cache = result_list

        return clone

    def json_path(self, field, json_object):
        values = []
        for obj in self:
            found = json_object.regex.find(getattr(obj, field, {}))
            vs = [i.value for i in found]
            if json_object.comparison in vs:
                values.append(obj)
        return values

    def _evaluate_json_lookup(self, item, lookup, value):
        oper = 'exact'

        evaluators = {
            'icontains': lambda item, value: item.lower() in value.lower(),
            'contains': lambda item, value: item in value,
            'in': lambda item, value: item in value,
            'iexact': lambda item, value: item.lower() == value.lower(),
            'exact': lambda item, value: item == value,
            'lt': lambda item, value: item < value,
            'lte': lambda item, value: item <= value,
            'gt': lambda item, value: item > value,
            'gte': lambda item, value: item >= value,
            'range': lambda item, value: item >= value[0] and item <= value[1],
        }

        def _getattr(obj, key):
            if isinstance(obj, dict):
                return obj[key]
            return getattr(obj, key)

        if lookup.split(LOOKUP_SEP)[-1] in evaluators.keys():
            oper = lookup.split(LOOKUP_SEP)[-1]
            lookup = LOOKUP_SEP.join(lookup.split(LOOKUP_SEP)[:-1])

        # DGT Verifica que el objeto json se un dictionario o lo convierte          
        field = getattr(item, lookup.split(LOOKUP_SEP)[0])
        if isinstance(field, dict):
            jdict = field
        elif isinstance(field, (six.string_types, six.text_type, bytes)):
            try:
                jdict = json.loads(field)
            except:
                return False
        else: return False

        for key in lookup.split(LOOKUP_SEP)[1:]:
            try:
                jdict = _getattr(jdict, key)
            except (AttributeError, KeyError):
                return False

        return evaluators[oper](jdict, value)

    def order_by(self, *args, **kwargs):
        # TODO: Dgt 1506 I d'nt find a way to know if the rs was filtered jsonfields
        # if self.json_lookups  : ...
        return self 

    def _clone(self, *args, **kwargs):
        clone = super(JSONAwareQuerySet, self)._clone(*args, **kwargs)
        clone.json_fields = self.json_fields
        # clone.json_lookups = getattr( self, 'json_lookups', False ) 

        return clone


class JSONAwareManager(models.Manager):
    
    def __init__(self, json_fields=None, *args, **kwargs):
        if not json_fields:
            json_fields = []
        self.json_fields = json_fields
        super(JSONAwareManager, self).__init__()

    def get_queryset(self):
        return JSONAwareQuerySet(self.json_fields, self.model)


# https://docs.djangoproject.com/en/1.8/topics/db/managers/#manager-names        