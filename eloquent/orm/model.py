# -*- coding: utf-8 -*-

import copy
import simplejson as json
import arrow
import inflection
from six import add_metaclass
from ..exceptions.orm import MassAssignmentError
from ..query import QueryBuilder
from .builder import Builder
from .collection import Collection


class MetaModel(type):

    def __getattr__(cls, item):
        try:
            return type.__getattribute__(cls, item)
        except AttributeError:
            query = cls.query()

            return getattr(query, item)


@add_metaclass(MetaModel)
class Model(object):

    __connection__ = None

    __table__ = None

    __primary_key__ = 'id'

    __incrementing__ = True

    __fillable__ = []
    __guarded__ = ['*']
    __unguarded__ = False

    __hidden__ = []
    __visible__ = []

    __timestamps__ = True

    __casts__ = {}

    _with = []

    _booted = {}

    __resolver = None

    CREATED_AT = 'created_at'
    UPDATED_AT = 'updated_at'

    def __init__(self, **attributes):
        """
        :param attributes: The instance attributes
        """
        self.__exists = False
        self.__dates = []
        self.__original = {}
        self.__attributes = {}

        self._boot_if_not_booted()

        self.sync_original()

        self.fill(**attributes)

    def _boot_if_not_booted(self):
        """
        Check if the model needs to be booted and if so, do it.
        """
        klass = self.__class__

        if not klass._booted.get(klass):
            klass._booted[klass] = True

            klass._boot()

    @classmethod
    def _boot(cls):
        """
        The booting method of the model.
        """
        # TODO

    def fill(self, **attributes):
        """
        Fill the model with attributes.

        :param attributes: The instance attributes
        :type attributes: dict

        :return: The model instance
        :rtype: Model

        :raises: MassAssignmentError
        """
        totally_guarded = self.totally_guarded()

        for key, value in self._fillable_from_dict(attributes).items():
            key = self._remove_table_from_key(key)

            if self.is_fillable(key):
                self.set_attribute(key, value)
            elif totally_guarded:
                raise MassAssignmentError(key)

        return self

    def force_fill(self, **attributes):
        """
        Fill the model with attributes. Force mass assignment.

        :param attributes: The instance attributes
        :type attributes: dict

        :return: The model instance
        :rtype: Model
        """
        self.unguard()

        self.fill(**attributes)

        self.reguard()

        return self

    def _fillable_from_dict(self, attributes):
        """
        Get the fillable attributes from a given dictionary.

        :type attributes: dict

        :return: The fillable attributes
        :rtype: dict
        """
        if self.__fillable__ and not self.__unguarded__:
            return {x: attributes[x] for x in attributes if x in self.__fillable__}

        return attributes

    def new_instance(self, attributes=None, exists=False):
        """
        Create a new instance for the given model.

        :param attributes: The instance attributes
        :type attributes: dict

        :param exists:
        :type exists: bool

        :return: A new instance for the current model
        :rtype: Model
        """
        if attributes is None:
            attributes = {}

        model = self.__class__(**attributes)

        model.set_exists(exists)

        return model

    def new_from_builder(self, attributes=None, connection=None):
        """
        Create a new model instance that is existing.

        :param attributes: The model attributes
        :type attributes: dict

        :param connection: The connection name
        :type connection: str

        :return: A new instance for the current model
        :rtype: Model
        """
        model = self.new_instance({}, True)

        if attributes is None:
            attributes = {}

        model.set_raw_attributes(attributes, True)

        model.set_connection(connection or self.__connection__)

        return model

    @classmethod
    def hydrate(cls, items, connection=None):
        """
        Create a collection of models from plain lists.

        :param items:
        :param connection:
        :return:
        """
        instance = cls().set_connection(connection)

        collection = instance.new_collection(items)

        return Collection(list(map(lambda item: instance.new_from_builder(item), collection)))

    @classmethod
    def hydrate_raw(cls, query, bindings=None, connection=None):
        """
        Create a collection of models from a raw query.

        :param query: The SQL query
        :type query: str

        :param bindings: The query bindings
        :type bindings: list

        :param connection: The connection name

        :rtype: Collection
        """
        instance = cls().set_connection(connection)

        items = instance.get_connection().select(query, bindings)

        return cls.hydrate(items, connection)

    @classmethod
    def create(cls, **attributes):
        """
        Save a new model an return the instance.

        :param attributes: The instance attributes
        :type attributes: dict

        :return: The new instance
        :rtype: Model
        """
        model = cls(**attributes)

        model.save()

        return model

    @classmethod
    def force_create(cls, **attributes):
        """
        Save a new model an return the instance. Allow mass assignment.

        :param attributes: The instance attributes
        :type attributes: dict

        :return: The new instance
        :rtype: Model
        """
        cls.unguard()

        model = cls.create(**attributes)

        cls.reguard()

        return model

    @classmethod
    def first_or_create(cls, **attributes):
        """
        Get the first record matching the attributes or create it.

        :param attributes: The instance attributes
        :type attributes: dict

        :return: The new instance
        :rtype: Model
        """
        instance = cls.where(attributes).first()

        if instance is not None:
            return instance

        return cls.create(**attributes)

    @classmethod
    def first_or_new(cls, **attributes):
        """
        Get the first record matching the attributes or instantiate it.

        :param attributes: The instance attributes
        :type attributes: dict

        :return: The new instance
        :rtype: Model
        """
        instance = cls.where(attributes).first()

        if instance is not None:
            return instance

        return cls(**attributes)

    @classmethod
    def update_or_create(cls, attributes, values=None):
        """
        Create or update a record matching the attributes, and fill it with values.

        :param attributes: The instance attributes
        :type attributes: dict

        :param values: The values
        :type values: dict

        :return: The new instance
        :rtype: Model
        """
        instance = cls.first_or_new(**attributes)

        if values is None:
            values = {}

        instance.fill(**values).save()

        return instance

    @classmethod
    def query(cls):
        """
        Begin querying the model.

        :return: A Builder instance
        :rtype: eloquent.orm.Builder
        """
        return cls().new_query()

    @classmethod
    def on(cls, connection=None):
        """
        Begin querying the model on a given connection.

        :param connection: The connection name
        :type connection: str

        :return: A Builder instance
        :rtype: eloquent.orm.Builder
        """
        instance = cls()

        instance.set_connection(connection)

        return instance.new_query()

    @classmethod
    def on_write_connection(cls):
        """
        Begin querying the model on the write connection.

        :return: A Builder instance
        :rtype: QueryBuilder
        """
        instance = cls()

        return instance.new_query().use_write_connection()

    @classmethod
    def all(cls, columns=None):
        """
        Get all og the models from the database.

        :param columns: The columns to retrieve
        :type columns: list

        :return: A Collection instance
        :rtype: Collection
        """
        instance = cls()

        return instance.new_query().get(columns)

    @classmethod
    def find(cls, id, columns=None):
        """
        Find a model by its primary key.

        :param id: The id of the model
        :type id: mixed

        :param columns: The columns to retrieve
        :type columns: list

        :return: Either a Model instance or a Collection
        :rtype: Model or Collection
        """
        instance = cls()

        if isinstance(id, list) and not id:
            return instance.new_collection()

        if columns is None:
            columns = ['*']

        return instance.new_query().find(id, columns)

    @classmethod
    def find_or_new(cls, id, columns=None):
        """
        Find a model by its primary key or return new instance.

        :param id: The id of the model
        :type id: mixed

        :param columns: The columns to retrieve
        :type columns: list

        :return: A Model instance
        :rtype: Model
        """
        instance = cls.find(id, columns)

        if instance is not None:
            return instance

        return cls()

    def fresh(self, with_=None):
        """
        Reload a fresh instance from the database.

        :param with_: The list of relations to eager load
        :type with_: list

        :return: The current model instance
        :rtype: Model
        """
        key = self.get_key_name()

        if self.exists:
            return self.__class__.with_(with_).where(key, self.get_key()).first()

    def load(self, relations):
        """
        Eager load relations on the model

        :param relations: The relations to eager load
        :type relations: str or list

        :return: The current model instance
        :rtype: Model
        """
        # TODO

    @classmethod
    def with_(cls, relations):
        """
        Begin querying a model with eager loading

        :param relations: The relations to eager load
        :type relations: str or list

        :return: A Builder instance
        :rtype: Builder
        """
        # TODO

    # TODO: Relations

    @classmethod
    def destroy(cls, *ids):
        """
        Destroy the models for the given IDs

        :param ids: The ids of the models to destroy
        :type ids: tuple

        :return: The number of models destroyed
        :rtype: int
        """
        count = 0

        if len(ids) == 1 and isinstance(ids[0], list):
            ids = ids[0]

        ids = list(ids)

        instance = cls()

        key = instance.get_key_name()

        for model in instance.new_query().where_in(key, ids).get():
            if model.delete():
                count += 1

        return count

    def delete(self):
        """
        Delete the model from the database.

        :rtype: bool or None

        :raises: Exception
        """
        if self.__primary_key__ is None:
            raise Exception('No primary key defined on the model.')

        if self.__exists:
            self._touch_owners()

            self._perform_delete_on_model()

            self.__exists = False

            return True

    def force_delete(self):
        """
        Force a hard delete on a soft deleted model.
        """
        return self.delete()

    def _perform_delete_on_model(self):
        """
        Perform the actual delete query on this model instance.
        """
        return self.new_query().where(self.get_key_name(), self.get_key()).delete()

    # TODO: events

    def _increment(self, column, amount=1):
        """
        Increment a column's value

        :param column: The column to increment
        :type column: str

        :param amount: The amount by which to increment
        :type amount: int

        :return: The new column value
        :rtype: int
        """
        return self._increment_or_decrement(column, amount, 'increment')

    def _decrement(self, column, amount=1):
        """
        Decrement a column's value

        :param column: The column to increment
        :type column: str

        :param amount: The amount by which to increment
        :type amount: int

        :return: The new column value
        :rtype: int
        """
        return self._increment_or_decrement(column, amount, 'decrement')

    def _increment_or_decrement(self, column, amount, method):
        """
        Runthe increment or decrement method on the model

        :param column: The column to increment or decrement
        :type column: str

        :param amount: The amount by which to increment or decrement
        :type amount: int

        :param method: The method
        :type method: str

        :return: The new column value
        :rtype: int
        """
        query = self.new_query()

        if not self.__exists:
            return getattr(query, method)(column, amount)

        self._increment_or_decrement_attribute_value(column, amount, method)

        query = query.where(self.get_key_name(), self.get_key())

        return getattr(query, method)(column, amount)

    def _increment_or_decrement_attribute_value(self, column, amount, method):
        """
        Increment the underlying attribute value and sync with original.

        :param column: The column to increment or decrement
        :type column: str

        :param amount: The amount by which to increment or decrement
        :type amount: int

        :param method: The method
        :type method: str

        :return: None
        """
        setattr(self, column, getattr(self, column) + (amount if method == 'increment' else amount * -1))

        self.sync_original_attribute(column)

    def update(self, **attributes):
        """
        Update the model in the database.

        :param attributes: The model attributes
        :type attributes: dict

        :return: The number of rows affected
        :rtype: int
        """
        if not self.__exists:
            return self.new_query().update(**attributes)

        return self.fill(**attributes).save()

    def push(self):
        """
        Save the model and all of its relationship.
        """
        # TODO

    def save(self, options=None):
        """
        Save the model to the database.
        """
        if options is None:
            options = {}

        query = self.new_query()

        if self.__exists:
            saved = self._perform_update(query, options)
        else:
            saved = self._perform_insert(query, options)

        if saved:
            self._finish_save(options)

        return saved

    def _finish_save(self, options):
        """
        Finish processing on a successful save operation.
        """
        self.sync_original()

        if options.get('touch', True):
            self._touch_owners()

    def _perform_update(self, query, options=None):
        """
        Perform a model update operation.

        :param query: A Builder instance
        :type query: Builder

        :param options: Extra options
        :type options: dict
        """
        if options is None:
            options = {}

        dirty = self.get_dirty()

        if len(dirty):
            # TODO: "updating" event
            if self.__timestamps__ and options.get('timestamps', True):
                self._update_timestamps()

            dirty = self.get_dirty()

            if len(dirty):
                self._set_keys_for_save_query(query).update(dirty)

                # TODO: "updated" event

        return True

    def _perform_insert(self, query, options=None):
        """
        Perform a model update operation.

        :param query: A Builder instance
        :type query: Builder

        :param options: Extra options
        :type options: dict
        """
        if options is None:
            options = {}

        # TODO: "creating" event

        if self.__timestamps__ and options.get('timestamps', True):
            self._update_timestamps()

        attributes = self.__attributes

        if self.__incrementing__:
            self._insert_and_set_id(query, attributes)
        else:
            query.insert(attributes)

        self.__exists = True

        # TODO: "created" event

        return True

    def _insert_and_set_id(self, query, attributes):
        """
        Insert the given attributes and set the ID on the model.

        :param query: A Builder instance
        :type query: Builder

        :param attributes: The attributes to insert
        :type attributes: dict
        """
        key_name = self.get_key_name()

        id = query.insert_get_id(attributes, key_name)

        self.set_attribute(key_name, id)

    def _touch_owners(self):
        """
        Touch the owning relations of the model.
        """
        # TODO

    def _set_keys_for_save_query(self, query):
        """
        Set the keys for a save update query.

        :param query: A Builder instance
        :type query: Builder

        :return: The Builder instance
        :rtype: Builder
        """
        query.where(self.get_key_name(), self._get_key_for_save_query())

        return query

    def _get_key_for_save_query(self):
        """
        Get the primary key value for a save query.
        """
        if self.get_key_name() in self.__original:
            return self.__original[self.get_key_name()]

        return self.__attributes[self.get_key_name()]

    def touch(self):
        """
        Update the model's timestamps.

        :rtype: bool
        """
        if not self.__timestamps__:
            return False

        self._update_timestamps()

        return self.save()

    def _update_timestamps(self):
        """
        Update the model's timestamps.
        """
        time = self.fresh_timestamp()

        if not self.is_dirty(self.UPDATED_AT):
            self.set_updated_at(time)

        if not self.__exists and not self.is_dirty(self.CREATED_AT):
            self.set_created_at(time)

    def set_created_at(self, value):
        """
        Set the value of the "created at" attribute.

        :param value: The value
        :type value: datetime
        """
        setattr(self, self.CREATED_AT, value)

    def set_updated_at(self, value):
        """
        Set the value of the "updated at" attribute.

        :param value: The value
        :type value: datetime
        """
        setattr(self, self.UPDATED_AT, value)

    def get_created_at_column(self):
        """
        Get the name of the "created at" column.

        :rtype: str
        """
        return self.CREATED_AT

    def get_updated_at_column(self):
        """
        Get the name of the "updated at" column.

        :rtype: str
        """
        return self.UPDATED_AT

    def fresh_timestamp(self):
        """
        Get a fresh timestamp for the model.

        :return: arrow.Arrow
        """
        return arrow.get()

    def new_query(self):
        """
        Get a new query builder for the model's table

        :return: A Builder instance
        :rtype: Builder
        """
        builder = self.new_orm_builder(
            self._new_base_query_builder()
        )

        return builder.set_model(self).with_(self._with)

    def new_orm_builder(self, query):
        """
        Create a new orm query builder for the model

        :param query: A QueryBuilder instance
        :type query: QueryBuilder

        :return: A Builder instance
        :rtype: Builder
        """
        return Builder(query)

    def _new_base_query_builder(self):
        """
        Get a new query builder instance for the connection.

        :return: A QueryBuilder instance
        :rtype: QueryBuilder
        """
        conn = self.get_connection()

        grammar = conn.get_query_grammar()

        return QueryBuilder(conn, grammar, conn.get_post_processor())

    def new_collection(self, models=None):
        """
        Create a new Collection instance.

        :param models: A list of models
        :type models: list

        :return: A new Collection instance
        :rtype: Collection
        """
        if models is None:
            models = []

        return Collection(models)

    def get_table(self):
        """
        Get the table associated with the model.

        :return: The name of the table
        :rtype: str
        """
        if self.__table__ is not None:
            return self.__table__

        return inflection.tableize(self.__class__.__name__)

    def set_table(self, table):
        """
        Set the table associated with the model.

        :param table: The table name
        :type table: str
        """
        self.__table__ = table

    def get_key(self):
        """
        Get the value of the model's primary key.
        """
        return self.get_attribute(self.get_key_name())

    def get_key_name(self):
        """
        Get the primary key for the model.

        :return: The primary key name
        :rtype: str
        """
        return self.__primary_key__

    def set_key_name(self, name):
        """
        Set the primary key for the model.

        :param name: The primary key name
        :type name: str
        """
        self.__primary_key__ = name

    def get_qualified_key_name(self):
        """
        Get the table qualified key name.

        :rtype: str
        """
        return '%s.%s' % (self.get_table(), self.get_key_name())

    def uses_timestamps(self):
        """
        Determine if the model uses timestamps.

        :rtype: bool
        """
        return self.__timestamps__

    def get_hidden(self):
        """
        Get the hidden attributes for the model.
        """
        return self.__hidden__

    def set_hidden(self, hidden):
        """
        Set the hidden attributes for the model.

        :param hidden: The attributes to add
        :type hidden: list
        """
        self.__hidden__ = hidden

        return self

    def add_hidden(self, *attributes):
        """
        Add hidden attributes to the model.

        :param attributes: The attributes to hide
        :type attributes: list
        """
        self.__hidden__ += attributes

    def get_visible(self):
        """
        Get the visible attributes for the model.
        """
        return self.__visible__

    def set_visible(self, visible):
        """
        Set the visible attributes for the model.

        :param visible: The attributes to make visible
        :type visible: list
        """
        self.__visible__ = visible

        return self

    def add_visible(self, *attributes):
        """
        Add visible attributes to the model.

        :param attributes: The attributes to make visible
        :type attributes: list
        """
        self.__visible__ += attributes

    def get_fillable(self):
        """
        Get the fillable attributes for the model.

        :rtype: list
        """
        return self.__fillable__

    def fillable(self, fillable):
        """
        Set the fillable attributes for the model.

        :param fillable: The fillable attributes
        :type fillable: list

        :return: The current Model instance
        :rtype: Model
        """
        self.__fillable__ = fillable

        return self

    def get_guarded(self):
        """
        Get the guarded attributes.
        """
        return self.__guarded__

    def guard(self, guarded):
        """
        Set the guarded attributes.

        :param guarded: The guarded attributes
        :type guarded: list

        :return: The current Model instance
        :rtype: Model
        """
        self.__guarded__ = guarded

        return self

    @classmethod
    def unguard(cls):
        """
        Disable the mass assigment restrictions.
        """
        cls.__unguarded__ = True

    @classmethod
    def reguard(cls):
        """
        Enable the mass assignment restrictions.
        :return:
        """
        cls.__unguarded__ = False

    def is_fillable(self, key):
        """
        Determine if the given attribute can be mass assigned.

        :param key: The attribute to check
        :type key: str

        :return: Whether the attribute can be mass assigned or not
        :rtype: bool
        """
        if self.__unguarded__:
            return True

        if key in self.__fillable__:
            return True

        if self.is_guarded(key):
            return False

        return not self.__fillable__ and not key.startswith('_')

    def is_guarded(self, key):
        """
        Determine if the given attribute is guarded.

        :param key: The attribute to check
        :type key: str

        :return: Whether the attribute is guarded or not
        :rtype: bool
        """
        return key in self.__guarded__ or self.__guarded__ == ['*']

    def totally_guarded(self):
        """
        Determine if the model is totally guarded.

        :rtype: bool
        """
        return len(self.__fillable__) == 0 and self.__guarded__ == ['*']

    def _remove_table_from_key(self, key):
        """
        Remove the table name from a given key.

        :param key: The key to remove the table name from.
        :type key: str

        :rtype: str
        """
        if '.' not in key:
            return key

        return key.split('.')[-1]

    def get_incrementing(self):
        return self.__incrementing__

    def set_incrementing(self, value):
        self.__incrementing__ = value

    def to_json(self, **options):
        """
        Convert the model instance to JSON.

        :param options: The JSON options
        :type options: dict

        :return: The JSON encoded model instance
        :rtype: str
        """
        return json.dumps(self.to_dict(), **options)

    def json_serialize(self):
        """
        Convert the object into something JSON serializable.

        :rtype: dict
        """
        return self.to_dict()

    def to_dict(self):
        """
        Convert the model instance to a dictionary.

        :return: The dictionary version of the model instance
        :rtype: dict
        """
        attributes = self.attributes_to_dict()

        attributes.update(self.relations_to_dict())

        return attributes

    def attributes_to_dict(self):
        """
        Convert the model's attributes to a dictionary.

        :rtype: dict
        """
        attributes = self._get_dictable_attributes()

        for key in self.get_dates():
            if not key in attributes:
                continue

            attributes[key] = self._format_date(self.as_datetime(attributes[key]))

        # TODO: mutators

        for key, value in self.__casts__.items():
            if key not in attributes:  # TODO: check mutators
                continue

            attributes[key] = self._cast_attribute(key, attributes[key])

        # TODO: appends

        return attributes

    def _get_dictable_attributes(self):
        """
        Get an attribute dictionary of all dictable attributes.

        :rtype: dict
        """
        return self._get_dictable_items(self.__attributes)

    def relations_to_dict(self):
        """
        Get the model's relationships in dictionary form.

        :rtype: dict
        """
        # TODO
        return {}

    def _get_dictable_items(self, values):
        """
        Get an attribute dictionary of all dictable values.

        :param values: The values to check
        :type values: dict

        :rtype: dict
        """
        if len(self.get_visible()) > 0:
            return {x: values[x] for x in values.keys() if x in self.get_visible()}

        return {x: values[x] for x in values.keys() if x not in self.get_hidden() and not x.startswith('_')}

    def get_attribute(self, key):
        """
        Get an attribute from the model.

        :param key: The attribute to get
        :type key: str
        """
        in_attributes = key in self.__attributes

        if in_attributes:
            return self._get_attribute_value(key)

        # TODO: relations

        raise AttributeError(key)

    def _get_attribute_value(self, key):
        """
        Get a plain attribute.

        :param key: The attribute to get
        :type key: str
        """
        value = self._get_attribute_from_dict(key)

        # TODO: mutators

        if self._has_cast(key):
            value = self._cast_attribute(key, value)
        elif key in self.get_dates():
            if value is not None:
                return self.as_datetime(value)

        return value

    def _get_attribute_from_dict(self, key):
        return self.__attributes.get(key)

    def has_get_mutator(self, key):
        """
        Determine if a get mutator exists for an attribute.

        :param key: The attribute name
        :type key: str

        :rtype: bool
        """
        return hasattr(self, 'get_%s_attribute' % inflection.underscore(key))

    def _has_cast(self, key):
        """
        Determine whether an attribute should be casted to a native type.

        :param key: The attribute to check
        :type key: str

        :rtype: bool
        """
        return key in self.__casts__

    def _is_json_castable(self, key):
        """
        Determine whether a value is JSON castable.

        :param key: The key to check
        :type key: str

        :rtype: bool
        """
        if self._has_cast(key):
            type = self._get_cast_type(key)

            return type in ['list', 'dict', 'json', 'object']

        return False

    def _get_cast_type(self, key):
        """
        Get the type of the cast for a model attribute.

        :param key: The attribute to get the cast for
        :type key: str

        :rtype: str
        """
        return self.__casts__[key].lower().strip()

    def _cast_attribute(self, key, value):
        """
        Cast an attribute to a native Python type

        :param key: The attribute key
        :type key: str

        :param value: The attribute value
        :type value: The attribute value

        :rtype: mixed
        """
        if value is None:
            return None

        type = self._get_cast_type(key)
        if type in ['int', 'integer']:
            return int(value)
        elif type in ['real', 'float', 'double']:
            return float(value)
        elif type in ['string', 'str']:
            return str(value)
        elif type in ['bool', 'boolean']:
            return bool(value)
        elif type in ['dict', 'list', 'json']:
            return json.loads(value)
        else:
            return value

    def get_dates(self):
        """
        Get the attributes that should be converted to dates.

        :rtype: list
        """
        defaults = [self.CREATED_AT, self.UPDATED_AT]

        return self.__dates + defaults

    def from_datetime(self, value):
        """
        Convert datetime to a datetime object

        :rtype: datetime.datetime
        """
        if isinstance(value, arrow.Arrow):
            return value.naive

        return arrow.get(value).naive

    def as_datetime(self, value):
        """
        Return a timestamp as a datetime.

        :rtype: arrow.Arrow
        """
        return arrow.get(value)

    def get_date_format(self):
        """
        Get the format to use for timestamps and dates.

        :rtype: str
        """
        return 'iso'

    def _format_date(self, date):
        """
        Format a date or timestamp.

        :param date: The date or timestamp
        :type date: datetime.datetime or datetime.date or arrow.Arrow

        :rtype: str
        """
        format = self.get_date_format()

        if format == 'iso':
            return date.isoformat()
        else:
            if isinstance(date, arrow.Arrow):
                return date.format(format)

            return date.strftime(format)

    def set_attribute(self, key, value):
        """
        Set a given attribute on the model.
        """
        # TODO: Set mutators

        if key in self.get_dates() and value:
            value = self.from_datetime(value)

        if self._is_json_castable(key):
            value = json.dumps(value)

        self.__attributes[key] = value

    def replicate(self, except_=None):
        """
        Clone the model into a new, non-existing instance.

        :param except_: The attributes that should not be cloned
        :type except_: list

        :rtype: Model
        """
        if except_ is None:
            except_ = [
                self.get_key_name(),
                self.get_created_at_column(),
                self.get_updated_at_column()
            ]

            attributes = {x: self.__attributes[x] for x in self.__attributes if x not in except_}

            instance = self.new_instance(attributes)

            # TODO: set relations

            return instance

    def get_attributes(self):
        """
        Get all of the current attributes on the model.

        :rtype: dict
        """
        return self.__attributes

    def set_raw_attributes(self, attributes, sync=False):
        """
        Set the dictionary of model attributes. No checking is done.

        :param attributes: The model attributes
        :type attributes: dict

        :param sync: Whether to sync the attributes or not
        :type sync: bool
        """
        self.__attributes = attributes

        if sync:
            self.sync_original()

    def get_original(self, key=None, default=None):
        """
        Get the original values

        :param key: The original key to get
        :type key: str

        :param default: The default value if the key does not exist
        :type default: mixed

        :rtype: mixed
        """
        if key is None:
            return self.__original

        return self.__original.get(key, default)

    def sync_original(self):
        """
        Sync the original attributes with the current.

        :rtype: Builder
        """
        self.__original = dict(self.__attributes.items())

        return self

    def sync_original_attribute(self, attribute):
        """
        Sync a single original attribute with its current value.

        :param attribute: The attribute to sync
        :type attribute: str

        :rtype: Model
        """
        self.__original[attribute] = self.__attributes[attribute]

        return self

    def is_dirty(self, *attributes):
        """
        Determine if the model or given attributes have been modified.

        :param attributes: The attributes to check
        :type attributes: list

        :rtype: boolean
        """
        dirty = self.get_dirty()

        if not attributes:
            return len(dirty) > 0

        for attribute in attributes:
            if attribute in dirty:
                return True

        return False

    def get_dirty(self):
        """
        Get the attribute that have been change since last sync.

        :rtype: list
        """
        dirty = {}

        for key, value in self.__attributes.items():
            if key not in self.__original:
                dirty[key] = value
            elif value != self.__original[key]:
                dirty[key] = value

        return dirty

    @property
    def exists(self):
        return self.__exists

    def set_exists(self, exists):
        self.__exists = exists

    def get_connection(self):
        """
        Get the database connection for the model

        :rtype: eloquent.connections.Connection
        """
        return self.resolve_connection(self.__connection__)

    def get_connection_name(self):
        """
        Get the database connection name for the model.

        :rtype: str
        """
        return self.__connection__

    def set_connection(self, name):
        """
        Set the connection associated with the model.

        :param name: The connection name
        :type name: str

        :return: The current model instance
        :rtype: Model
        """
        self.__connection__ = name

        return self

    @classmethod
    def resolve_connection(cls, connection=None):
        """
        Resolve a connection instance.

        :param connection: The connection name
        :type connection: str

        :rtype: eloquent.connections.Connection
        """
        return cls.__resolver.connection(connection)

    @classmethod
    def get_connection_resolver(cls):
        """
        Get the connection resolver instance.
        """
        return cls.__resolver

    @classmethod
    def set_connection_resolver(cls, resolver):
        """
        Set the connection resolver instance.
        """
        cls.__resolver = resolver

    @classmethod
    def unset_connection_resolver(cls, resolver):
        """
        Unset the connection resolver instance.
        """
        cls._resolver = None

    def __getattr__(self, item):
        try:
            return super(Model, self).__getattribute__(item)
        except AttributeError:
            return self.get_attribute(item)

    def __setattr__(self, key, value):
        if key.startswith(('_Model__', '_%s__' % self.__class__.__name__, '__')):
            super(Model, self).__setattr__(key, value)
        elif callable(getattr(self, key, None)):
            return super(Model, self).__setattr__(key, value)
        else:
            self.set_attribute(key, value)

    def __delattr__(self, item):
        try:
            del self.__attributes[item]
        except KeyError:
            raise AttributeError(item)