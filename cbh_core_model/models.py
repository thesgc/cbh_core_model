# -*- coding: utf-8 -*-
from django.db import models, connection

from solo.models import SingletonModel
from django_extensions.db.models import TimeStampedModel
from django.db.models.signals import post_save
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import Permission, User, Group
from collections import OrderedDict
from django.utils.functional import cached_property
from copy import copy
import json
import dateutil
import time

def get_all_hstore_values(table, column, key, is_list=False, extra_where=" True"):
    '''Using an hstore query from the reference here
    http://www.youlikeprogramming.com/2012/06/mastering-the-postgresql-hstore-date-type/
    where project_id = {{project_id}}
    '''
    cursor = connection.cursor()
    sql = u"SELECT DISTINCT {column} -> '{key}' FROM {table} where {column} -> '{key}' != '' and {extra_where};".format(
        **{"table": unicode(table), "key": unicode(key), "column": unicode(column),  "extra_where": unicode(extra_where)})
    cursor.execute(sql)
    mytuple = cursor.fetchall()
    items = []
    data = [d[0] for d in mytuple]
    for d in data:
        if is_list:
            try:
                for elem in json.loads(d):
                    items.append(elem)
            except ValueError:
                items.append(d)
            except TypeError:
                items.append(d)
        else:
            items.append(d)
    return items

PROJECT_PERMISSIONS = (("viewer", "Can View"),
                       ("editor", "Can edit or add batches"),
                       ("admin", "Can assign permissions"))


class ProjectPermissionManager(models.Manager):

    def sync_all_permissions(self):
        for perm in self.all():
            perm.sync_permissions()

    def get_user_permission(self, project_id, user, codenames, perms=None):
        '''Check the given users' permissions against a list of codenames for a project id'''
        if not perms:
            perms = user.get_all_permissions()
        codes = ["%d.%s" % (project_id, codename) for codename in codenames]
        matched = list(perms.intersection(codes))
        if len(matched) > 0:
            return True
        return False


class ProjectPermissionMixin(models.Model):

    '''The aim of this mixin is to create a permission content type and a permission model for a given project
    It allows for pruning the contnet types once the model is changed
    '''

    objects = ProjectPermissionManager()

    def get_project_key(self):
        return str(self.pk)

    def sync_permissions(self):
        '''first we delete the existing permissions that are not labelled in the model'''
        ct, created = ContentType.objects.get_or_create(
            app_label=self.get_project_key(), model=self, name=self.name)
        deleteable_permissions = Permission.objects.filter(content_type_id=ct.pk).exclude(
            codename__in=[perm[0] for perm in PROJECT_PERMISSIONS])
        deleteable_permissions.delete()
        for perm in PROJECT_PERMISSIONS:
            pm = Permission.objects.get_or_create(
                content_type_id=ct.id, codename=perm[0], name=perm[1])

    def get_contenttype_for_instance(self):
        ct = ContentType.objects.get(
            app_label=self.get_project_key(), model=self)
        return ct

    def delete_all_instance_permissions(self):
        '''for the pre delete signal'''
        deleteable_permissions = Permission.objects.filter(
            content_type_id=self.get_contenttype_for_instance().id)
        deleteable_permissions.delete()

    def get_instance_permission_by_codename(self, codename):
        pm = Permission.objects.get(
            codename=codename, content_type_id=self.get_contenttype_for_instance().id)
        return pm

    def _add_instance_permissions_to_user_or_group(self, group_or_user, codename):
        if type(group_or_user) == Group:
            group_or_user.permissions.add(
                self.get_instance_permission_by_codename(codename))
        if type(group_or_user) == User:
            group_or_user.user_permissions.add(
                self.get_instance_permission_by_codename(codename))

    def make_editor(self, group_or_user):
        self._add_instance_permissions_to_user_or_group(
            group_or_user, "editor")

    def make_viewer(self, group_or_user):
        self._add_instance_permissions_to_user_or_group(
            group_or_user, "viewer")

    def make_admin(self, group_or_user):
        self._add_instance_permissions_to_user_or_group(group_or_user, "admin")

    class Meta:

        abstract = True


class ProjectType(TimeStampedModel):

    ''' Allows configuration of parts of the app on a per project basis - initially will be used to separate out compound and inventory projects '''
    name = models.CharField(
        max_length=100, db_index=True, null=True, blank=True, default=None)
    show_compounds = models.BooleanField(default=True)

    def __unicode__(self):
        return self.name


class DataType(TimeStampedModel):
    name = models.CharField(unique=True, max_length=500)
    uri = models.CharField(max_length=1000, default="")
    version = models.CharField(max_length=10, default="")

    def get_space_replaced_name(self):
        return self.name.replace(u" ", u"__space__")

    def __unicode__(self):
        return self.name


class CustomFieldConfig(TimeStampedModel):
    name = models.CharField(unique=True, max_length=500)
    created_by = models.ForeignKey("auth.User")
    schemaform = models.TextField(default="", null=True, blank=True, )
    data_type = models.ForeignKey(
        DataType, null=True, blank=True, default=None)
    #objects = CustomFieldConfigManager()

    def __unicode__(self):
        return self.name

    def get_space_replaced_name(self):
        return self.name.replace(u" ", u"__space__")


class DataFormConfig(TimeStampedModel):

    '''Shared configuration object - all projects can see this and potentially use it
    Object name comes from a concatentaion of all of the levels of custom field config
    '''
    created_by = models.ForeignKey("auth.User")
    human_added = models.NullBooleanField(default=True)
    parent = models.ForeignKey(
        'self', related_name='children', default=None, null=True, blank=True)

    l0 = models.ForeignKey("cbh_core_model.CustomFieldConfig",
                           related_name="l0",
                           help_text="The first level in the hierarchy of the form you are trying to create. For example, if curating industries, companies,  employees , teams and departments, l0 would be industries.")
    l1 = models.ForeignKey("cbh_core_model.CustomFieldConfig",
                           related_name="l1",
                           null=True,
                           blank=True,
                           default=None,
                           help_text="The second level in the hierarchy of the form you are trying to create. For example, if curating industries, companies,  employees , teams and departments, l1 would be companies.")
    l2 = models.ForeignKey("cbh_core_model.CustomFieldConfig",
                           related_name="l2", null=True, blank=True, default=None,
                           help_text="The third level in the hierarchy of the form you are trying to create. For example, if curating industries, companies,  employees , teams and departments, l2 would be departments.")
    l3 = models.ForeignKey("cbh_core_model.CustomFieldConfig",
                           related_name="l3",
                           null=True,
                           blank=True,
                           default=None,
                           help_text="The forth level in the hierarchy of the form you are trying to create. For example, if curating industries, companies,  employees , teams and departments, l3 would be teams.")
    l4 = models.ForeignKey("cbh_core_model.CustomFieldConfig",
                           related_name="l4",
                           null=True,
                           blank=True,
                           default=None,
                           help_text="The fifth level in the hierarchy of the form you are trying to create. For example, if curating industries, companies,  employees , teams and departments, l4 would be employees.")

    def __unicode__(self):
        string = ""
        if self.l0:
            string += self.l0.__unicode__()
        if self.l1:
            string += " >> " + self.l1.__unicode__()
        if self.l2:
            string += " >> " + self.l2.__unicode__()
        if self.l3:
            string += " >> " + self.l3.__unicode__()
        if self.l4:
            string += " >> " + self.l4.__unicode__()
        return string

    class Meta:
        unique_together = (('l0', 'l1', 'l2', 'l3', 'l4'),)
        ordering = ('l0', 'l1', 'l2', 'l3', 'l4')

    def last_level(self):
        last_level = ""
        if self.l4_id is not None:
            return "l4"
        if self.l3_id is not None:
            return "l3"
        if self.l2_id is not None:
            return "l2"
        if self.l1_id is not None:
            return "l1"
        if self.l0_id is not None:
            return "l0"
        return last_level

    def get_all_ancestor_objects(obj, request, tree_builder={}, uri_stub=""):
        levels = ["l0", "l1", "l2", "l3", "l4"]
        levels = ["%s_id" % l for l in levels]
        used_levels = []
        for lev in levels:
            if getattr(obj, lev) is not None and lev != "%s_id" % obj.last_level():
                used_levels.append(lev)

        filters = []
        for i in range(1, len(used_levels)+1):
            level_name = used_levels[i-1]
            level_filters = {lev: getattr(obj, lev) for lev in used_levels[:i]}
            filters.insert(0, level_filters)

        for index, filter_set in enumerate(filters):
            defaults = {lev: None for lev in levels}
            new_filters = defaults.update(filter_set)

            defaults["defaults"] = {"created_by_id": request.user.id,
                                    "human_added": False}
            new_object, created = DataFormConfig.objects.get_or_create(
                **defaults)
            if not obj.parent_id:
                obj.parent_id = new_object.id
                print obj.parent_id
                obj.save()
#

            permitted_child_array = tree_builder.get(
                "%s/%d" % (uri_stub, new_object.id), [])
            permitted_child_array.append(obj)
            tree_builder[
                "%s/%d" % (uri_stub, new_object.id)] = list(set(permitted_child_array))

            obj = new_object
            if index == len(filters) - 1:
                tree_builder["root"] = [obj]


class Project(TimeStampedModel, ProjectPermissionMixin):

    ''' Project is a holder for moleculedictionary objects and for batches'''
    name = models.CharField(
        max_length=100, db_index=True, null=True, blank=True, default=None)
    project_key = models.SlugField(
        max_length=50, db_index=True, null=True, blank=True, default=None, unique=True)
    created_by = models.ForeignKey("auth.User")
    custom_field_config = models.ForeignKey(
        "cbh_core_model.CustomFieldConfig", related_name="project", null=True, blank=True, default=None, )
    project_type = models.ForeignKey(
        ProjectType, null=True, blank=True, default=None)
    is_default = models.BooleanField(default=False)
    enabled_forms = models.ManyToManyField(DataFormConfig, blank=True)

    class Meta:
        get_latest_by = 'created'

    def __unicode__(self):
        return self.name

    @models.permalink
    def get_absolute_url(self):
        return {'post_slug': self.project_key}


def sync_permissions(sender, instance, created, **kwargs):
    '''After saving the project make sure it has entries in the permissions table'''
    if created is True:
        instance.sync_permissions()

        instance.make_editor(instance.created_by)

post_save.connect(sync_permissions, sender=Project, dispatch_uid="proj_perms")


class SkinningConfig(SingletonModel):

    '''Holds information about custom system messages and other customisable elements'''
    #created_by = models.ForeignKey("auth.User")
    instance_alias = models.CharField(
        max_length=50, null=True, blank=False, default='ChemReg')
    project_alias = models.CharField(
        max_length=50, null=True, blank=False, default='project')
    result_alias = models.CharField(
        max_length=50, null=True, blank=False, default='result')
    file_errors_from_backend = models.NullBooleanField(default=False)
    enable_smiles_input = models.NullBooleanField(default=True)
    data_manager_email = models.CharField(max_length=100, default="")
    data_manager_name = models.CharField(max_length=100, default="")
    def __unicode__(self):
        return u"Skinning Configuration"

    class Meta:
        verbose_name = "Skinning Configuration"
    # we can eventually use this to specify different chem sketching tools


# class DataTransformation(TimeStampedModel):
#     name = models.CharField(max_length=100, null=True, blank=True, default=None)
#     uri = models.CharField(max_length=1000, null=True, blank=True, default=None)
#     target_repository_api
#     patch = models.TextField()

#     def __unicode__(self):
#         return "%s - %s" % (self.name, self.uri)

def test_string(value):
    return True

def test_bool(value):
    return False



def test_int(value):
    try:
        floatval = float(value)
        intval = int(value)
        if intval == floatval and "." not in unicode(value):
            return True
    except  ValueError:
        return False

def test_number(value):
    try:
        floatval = float(value)
        return True
    except  ValueError:
        return False


def test_stringdate(value):
    try:
        curated_value = dateutil.parser.parse(unicode(value)).strftime("%Y-%m-%d")
        return curated_value
    except ValueError:
        return False

def test_percentage(value):
    result = test_number(value)
    if result:
        if float(val) > 0 and float(val) < 100:
            return True
    return False


class PinnedCustomField(TimeStampedModel):
    TEXT = "text"
    TEXTAREA = "textarea"
    UISELECT = "uiselect"
    INTEGER = "integer"
    NUMBER = "number"
    UISELECTTAG = "uiselecttag"
    UISELECTTAGS = "uiselecttags"
    CHECKBOXES = "checkboxes"
    PERCENTAGE = "percentage"
    DECIMAL = "decimal"
    BOOLEAN = "boolean"
    DATE = "date"
    IMAGE = "imghref"
    LINK = "href"

    def pandas_converter(self, field_length, pandas_dtype):
        dtype = str(pandas_dtype)
        if dtype == "int64":
            return self.INTEGER
        if dtype == "float64":
            return self.NUMBER
        if dtype == "object":
            if field_length > 100:
                return self.TEXTAREA
            else:
                return self.TEXT
        return self.TEXT

    FIELD_TYPE_CHOICES = OrderedDict((
        (TEXT, {"name": "Short text field", "data": {
         "type": "string", "icon": "<span class ='glyphicon glyphicon-font'></span>"}, "test_datatype" : test_string}
         ),
        ("char", {
            "name": "Short text field", "data": {"type": "string"}, "test_datatype" : test_string}),
        (TEXTAREA, {"name": "Full text", "data": {
         "icon": "<span class ='glyphicon glyphicon-font'></span>", "type": "string", "format": "textarea"}, "test_datatype" : test_string}),
        (UISELECT, {"name": "Choice field", "data": {
         "type": "string", "format": "uiselect"}, "test_datatype" : test_string}),
        (INTEGER, {"name": "Integer field", "data": {
         "icon": "<span class ='glyphicon glyphicon-stats'></span>", "type": "integer"}, "test_datatype" : test_int}),
        (NUMBER, {"name": "Decimal field", "data": {
         "icon": "<span class ='glyphicon glyphicon-sound-5-1'></span>", "type": "number"}, "test_datatype": test_number}),
        (UISELECTTAG, {"name": "Choice allowing create", "data":  {
         "icon": "<span class ='glyphicon glyphicon-tag'></span>", "type": "string", "format": "uiselect", "options":{}}, "test_datatype" : test_string}),
        (UISELECTTAGS, {"name": "Tags field allowing create", "data": {"icon": "<span class ='glyphicon glyphicon-tags'></span>", "type": "array", "format": "uiselect", "options": {
            "tagging": "tagFunction",
            "taggingLabel": "(adding new)",
            "taggingTokens": "ENTER",
            'refreshDelay': 10
        }}, "test_datatype" : test_string}),
        (PERCENTAGE, {"name": "Percentage field", "data": {
         "icon": "<span class ='glyphicon'>%</span>", "type": "number", "maximum": 100.0, "minimum": 0.1}, "test_datatype": test_percentage}),
        (DATE,  {"name": "Date Field", "data": {
         "icon": "<span class ='glyphicon glyphicon-calendar'></span>", "type": "string",   "format": "date"}, "test_datatype": test_stringdate}),
        (LINK, {"name": "Link to server or external", "data": {"format": "href", "type":
                                                               "string", "icon": "<span class ='glyphicon glyphicon glyphicon-new-window'></span>"}, "test_datatype" : test_string}),
        (IMAGE, {"name": "Image link to embed", "data": {"format": "imghref", "type":
                                                         "string", "icon": "<span class ='glyphicon glyphicon glyphicon-picture'></span>"},  "test_datatype" : test_string}),
        (DECIMAL, {"name": "Decimal field", "data": {
         "icon": "<span class ='glyphicon'>3.1</span>", "type": "number"},  "test_datatype" : test_number}),
        (BOOLEAN, {"name": "checkbox", "data": {
         "icon": "<span class ='glyphicon'>3.1</span>", "type": "boolean"},"test_datatype" : test_bool }),
        ("related", {"name": "TEST", "data": {
         "icon": "<span class ='glyphicon'>3.1</span>", "type": "string"}, "test_datatype" : test_string})

    ))

    field_key = models.CharField(max_length=500,  default="")
    name = models.CharField(max_length=500)
    description = models.CharField(
        max_length=1024, blank=True, null=True, default="")
    custom_field_config = models.ForeignKey(
        "cbh_core_model.CustomFieldConfig", related_name='pinned_custom_field', default=None, null=True, blank=True)
    required = models.BooleanField(default=False)
    part_of_blinded_key = models.BooleanField(
        default=False, verbose_name="blind key")
    field_type = models.CharField(default="char", choices=(
        (name, value["name"]) for name, value in FIELD_TYPE_CHOICES.items()), max_length=15, )
    allowed_values = models.CharField(
        max_length=1024, blank=True, null=True, default="")
    position = models.PositiveSmallIntegerField()
    default = models.CharField(max_length=500, default="", blank=True)

    pinned_for_datatype = models.ForeignKey(
        DataType, blank=True, null=True, default=None)
    standardised_alias = models.ForeignKey(
        "self", related_name="alias_mapped_from", blank=True, null=True, default=None)
    attachment_field_mapped_to = models.ForeignKey(
        "self", related_name="attachment_field_mapped_from", blank=True, null=True, default=None)

    def validate_field(self, value):
        if not value and self.required:
            return False
        else:
            func = self.FIELD_TYPE_CHOICES[self.field_type]["test_datatype"]
            return func(value)

    # data_transformation = models.ForeignKey("cbh_core_model.DataTransformation",
    #     related_name="pinned_custom_field",
    #     default=None, blank=True)

    def get_dropdown_list(self, projectKey):
        is_array = False
        if self.FIELD_TYPE_CHOICES[self.field_type]["data"]["type"] == "array":
            is_array = True
        db_items = get_all_hstore_values("cbh_chembl_model_extension_cbhcompoundbatch  inner join cbh_core_model_project on cbh_core_model_project.id = cbh_chembl_model_extension_cbhcompoundbatch.project_id ",
                                         "custom_fields",
                                         self.name,
                                         is_list=is_array,
                                         extra_where="cbh_core_model_project.project_key ='%s'" % projectKey)
        return [item for item in db_items]

    def get_allowed_items(self, projectKey):
        items = [item.strip()
                 for item in self.allowed_values.split(",") if item.strip()]
        setitems = sorted(
            list(set(items + self.get_dropdown_list(projectKey))))
        testdata = [{"label": item.strip(), "value": item.strip()}
                    for item in setitems if item]
        searchdata = [{"label": "[%s] %s" % (self.name, item.strip()), "value": "%s|%s" % (
            self.name, item.strip())} for item in setitems if item]
        return (testdata, searchdata)

    @cached_property
    def get_items_simple(self):
        items = [item.strip()
                 for item in self.allowed_values.split(",") if item.strip()]
        setitems = sorted(list(set(items)))
        testdata = [{"label": item.strip(), "value": item.strip()}
                    for item in setitems if item]
        return testdata

    @cached_property
    def get_space_replaced_name(self):
        return self.name.replace(u" ", u"__space__")

    def __unicode__(self):
        return "%s  %s  %s" % (self.name, self.field_key,  self.field_type)

    @cached_property
    def field_values(obj):
        data = copy(obj.FIELD_TYPE_CHOICES[obj.field_type]["data"])

        data["title"] = obj.name
        data["placeholder"] = obj.description
        form = {}
        form["position"] = obj.position
        form["key"] = obj.get_space_replaced_name
        form["title"] = obj.name

        form["description"] = obj.description
        form["disableSuccessState"] = True
        form["feedback"] = False
        # form["allowed_values"] = obj.allowed_values
        # form["part_of_blinded_key"] = obj.part_of_blinded_key
        searchitems = []
        
        if data["type"] == "array":
            data['default'] = obj.default.split(",")
        if obj.UISELECT in data.get("format", ""):

            form["placeholder"] = "Choose..."
            form["help"] = obj.description
            data['items'] = obj.get_items_simple
            form['permanent_items'] = obj.get_items_simple

        if obj.default:
            data['default'] = obj.default
        if obj.UISELECTTAGS == obj.field_type:
            form["description"] = "Hit enter twice to add a new item or search existing items in the dropdown."

        if obj.UISELECTTAGS == obj.field_type:
            #set default to empty array or CSV from default field
            data["default"] = []


        if data.get("format", False) == obj.DATE:
            maxdate = time.strftime("%Y-%m-%d")
            form.update({
                "minDate": "2000-01-01",
                "maxDate": maxdate,
                'type': 'datepicker',
                "format": "yyyy-mm-dd",
                'pickadate': {
                    'selectYears': True,
                    'selectMonths': True,
                },
            })

        else:
            for item in ["options"]:
                stuff = data.pop(item, None)
                if stuff:
                    form[item] = stuff
        return (data, form)

    class Meta:
        ordering = ['position']
        get_latest_by = 'created'


class Invitation(TimeStampedModel):
    email = models.CharField(max_length=100)
    created_by = models.ForeignKey("auth.User")
    first_name = models.TextField(default="", null=True, blank=True, )
    last_name = models.TextField(default="", null=True, blank=True, )
    projects = models.ManyToManyField("cbh_core_model.Project", blank=True)

    def __unicode__(self):
        return self.name