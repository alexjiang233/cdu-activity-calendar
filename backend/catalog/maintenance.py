"""Typed maintenance screens sharing the workbench, permissions and revision log."""
import gzip
import json
from uuid import uuid4
from functools import wraps
from urllib.parse import urlencode

from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.forms import AdminPasswordChangeForm, UserCreationForm
from django.contrib.auth.models import Group
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import transaction, IntegrityError
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from . import audit, indexing
from .models import (ActivityGroup, Source, Taxonomy, NoticeTaxonomy, Fact, GuideSection,
                     GuideBlock, GuideFaq, GuideSource, Profile, ImportBatch, ChangeLog,
                     DraftChange, SiteMeta, Notice, Activity, Guide, CampusService, Revision)
from .workbench import guard, shell

# Public content has dedicated editors. These are supporting records, not a second admin.
REGISTRY = {
 'notice':(Notice,'通知版本',('activity','source','year','published','deadline','deadline_kind','stage_start','stage_end','audience','conflict','display_activity','position','visibility'),('activity__title','source__title','source__url','audience'),('activity',)),
 'fact':(Fact,'分条信息',('notice','kind','label','value','quote','locator','source_url','basis','position'),('value','quote','notice__activity__title'),('notice',)),
 'source':(Source,'公告来源',('url','title','publisher'),('title','url','publisher'),()),
 'taxonomy':(Taxonomy,'分类与学院标签',('kind','label','code','position'),('label','code'),('kind',)),
 'notice-tag':(NoticeTaxonomy,'通知标签',('notice','taxonomy','position'),('notice__activity__title','taxonomy__label'),('notice',)),
 'group':(ActivityGroup,'学院展示分组',('title','activity','colleges','notices','tags','visibility','position'),('title','activity__title'),('activity',)),
 'section':(GuideSection,'指南步骤',('guide','title','kind','position'),('title','guide__title'),('guide',)),
 'block':(GuideBlock,'指南条目',('section','text','kind','position'),('text','section__guide__title'),('section',)),
 'faq':(GuideFaq,'指南问答',('guide','question','answer','position'),('question','answer','guide__title'),('guide',)),
 'guide-source':(GuideSource,'指南资料来源',('guide','label','url','page_ref','checked_on','note'),('label','guide__title','url'),('guide',)),
 'profile':(Profile,'原文结构档案',(),('notice__activity__title',),('notice',)),
 'batch':(ImportBatch,'导入记录',(),('id','note','status'),()),
 'change':(ChangeLog,'逐项变更记录',(),('entity_id','note','action'),()),
 'draft':(DraftChange,'全部草稿记录',(),('entity_id','note','status'),('status',)),
 'site':(SiteMeta,'站点设置',('site_name','description','schema_version','coverage','policies','display_options'),('site_name',),()),
 'user':(get_user_model(),'维护者账号',('username','first_name','last_name','email','is_active','is_staff','is_superuser','groups','user_permissions'),('username','email'),()),
 'role':(Group,'权限组',('name','permissions'),('name',),()),
}
READONLY={'profile','batch','change','draft'}
AUTH={'user','role'}
JSON_FIELDS={'coverage','policies','display_options'}


def config(code):
    if code not in REGISTRY:raise Http404
    return REGISTRY[code]


def permitted(user,code,action='view'):
    model=config(code)[0]
    if code in AUTH:return user.is_superuser
    return user.has_perm(f'{model._meta.app_label}.{action}_{model._meta.model_name}')


def secure(view):
    @guard()
    @wraps(view)
    def inner(request,*args,**kwargs):
        code=kwargs.get('code')
        if code and not permitted(request.user,code):raise PermissionDenied
        return view(request,*args,**kwargs)
    return inner


def label(obj):
    for field in ('title','name','question','label','value','text','url','username','site_name','note'):
        value=getattr(obj,field,None)
        if value:return str(value)[:120]
    if isinstance(obj,Notice):return f'{obj.activity.title} · {obj.year or "年份未列"}'
    if isinstance(obj,GuideBlock):return obj.text[:120]
    return str(obj)


def row_snapshot(obj):
    # Authentication hashes and session credentials never enter revision snapshots.
    if isinstance(obj,get_user_model()):
        keys=REGISTRY['user'][2]
    elif isinstance(obj,SiteMeta):keys=REGISTRY['site'][2]
    else:keys=[f.name for f in obj._meta.concrete_fields if f.name not in ('created_at','updated_at')]
    data={}
    for key in keys:
        field=obj._meta.get_field(key)
        if field.many_to_many:data[key]=sorted(getattr(obj,key).values_list('pk',flat=True))
        else:data[key]=audit._jsonable(getattr(obj,field.attname))
    for field in obj._meta.many_to_many:
        if field.name not in data and not field.remote_field.through._meta.auto_created:continue
        data[field.name]=sorted(getattr(obj,field.name).values_list('pk',flat=True))
    return data


def refresh(obj):
    if isinstance(obj,Notice):indexing.refresh_notice(obj)
    elif isinstance(obj,Activity):indexing.refresh_activity(obj)
    elif isinstance(obj,(Fact,Profile,NoticeTaxonomy)):
        if Notice.objects.filter(pk=obj.notice_id).exists():indexing.refresh_notice(Notice.objects.get(pk=obj.notice_id))
    elif isinstance(obj,Source):
        for notice in obj.notices.all().iterator():indexing.refresh_notice(notice)
    elif isinstance(obj,Taxonomy):
        for activity in obj.activities.all().iterator():indexing.refresh_activity(activity)


def record(code,pk,before,after,actor,action='update'):
    if before==after:return None
    rev=audit.open_revision(f'{"新增" if action=="create" else "移除" if action=="delete" else "修改"}：{config(code)[1]}',
        'workbench',actor=actor,payload={'maintenance':code,'id':str(pk),'before':before,'after':after})
    audit.log_change(rev,code,str(pk),action,before,after,actor=actor,note=rev.reason)
    audit.publish_revision(rev)
    return rev


class CommaList(forms.CharField):
    def prepare_value(self,value):return '，'.join(map(str,value)) if isinstance(value,list) else value
    def clean(self,value):
        value=super().clean(value)
        return [s.strip() for s in value.replace('，',',').replace('、',',').split(',') if s.strip()]


def form_class(code):
    model,_,fields,_,_=config(code)
    fields=list(fields)
    declared={}
    for name in fields:
        field=model._meta.get_field(name)
        if name in ('tags',):declared[name]=CommaList(label=field.verbose_name,required=False)
        elif field.get_internal_type()=='DateField':
            declared[name]=forms.DateField(label=field.verbose_name,required=not field.blank,
                widget=forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d'))
        elif field.get_internal_type()=='DateTimeField':
            declared[name]=forms.DateTimeField(label=field.verbose_name,required=not field.blank,
                input_formats=['%Y-%m-%dT%H:%M','%Y-%m-%dT%H:%M:%S'],
                widget=forms.DateTimeInput(attrs={'type':'datetime-local'},format='%Y-%m-%dT%H:%M'))
    def init(self,*args,**kwargs):
        forms.ModelForm.__init__(self,*args,**kwargs)
        for field in self.fields.values():
            if isinstance(field,(forms.ModelChoiceField,forms.ModelMultipleChoiceField)):
                field.label_from_instance=label
                if field.queryset.model is Notice:field.queryset=field.queryset.select_related('activity')
        if code=='taxonomy':self.fields['code'].required=False
    declared['__init__']=init
    def clean(self):
        data=forms.ModelForm.clean(self)
        if code=='group' and data.get('activity') and data.get('notices') is not None:
            notices=data['notices'];activity=data['activity']
            if notices.exclude(Q(display_activity=activity)|Q(display_activity__isnull=True,activity=activity)).exists():
                self.add_error('notices','请选择属于该活动的通知；先在通知版本中核对展示归属。')
            if data.get('visibility')=='public' and ActivityGroup.objects.filter(visibility='public',notices__in=notices).exclude(pk=self.instance.pk).exists():
                self.add_error('notices','部分通知已属于另一个公开分组，不能在两个入口重复展示。')
        if code=='notice' and data.get('stage_start') and data.get('stage_end') and data['stage_end']<data['stage_start']:
            self.add_error('stage_end','结束日期不能早于开始日期。')
        return data
    declared['clean']=clean
    if code=='taxonomy':
        declared['clean_code']=lambda self:self.cleaned_data['code'] or 'manual-'+uuid4().hex[:16]
    return forms.modelform_factory(model,fields=fields,form=type('Fields',(forms.ModelForm,),declared))


@secure
def index(request):
    groups=[('内容关系',['notice','fact','source','group','notice-tag','taxonomy']),
            ('校园指南',['section','block','faq','guide-source']),
            ('记录与站点',['draft','change','batch','profile','site']),('账号与权限',['user','role'])]
    cards=[]
    for title,codes in groups:
        items=[{'title':config(c)[1],'url':reverse('maintenance:list',args=[c]),
                'count':config(c)[0].objects.count(),'readonly':c in READONLY} for c in codes if permitted(request.user,c)]
        if items:cards.append((title,items))
    return render(request,'workbench/settings.html',shell(request,active='settings',title='设置与维护',groups=cards))


@secure
def listing(request,code):
    model,title,fields,search,filters=config(code)
    qs=model.objects.all()
    if code in ('notice','fact','profile','notice-tag'):qs=qs.select_related('activity' if code=='notice' else 'notice__activity')
    q=request.GET.get('q','').strip()[:120]
    if q:
        expression=Q()
        for key in search:expression|=Q(**{key+'__icontains':q})
        qs=qs.filter(expression)
    for key in filters:
        if request.GET.get(key):qs=qs.filter(**{key:request.GET[key]})
    qs=qs.order_by('-created_at' if any(f.name=='created_at' for f in model._meta.fields) else 'pk')
    page=Paginator(qs,20).get_page(request.GET.get('page'))
    args=request.GET.copy();args.pop('page',None)
    rows=[{'obj':obj,'label':label(obj),'id':obj.pk,'url':reverse('maintenance:edit',args=[code,obj.pk])} for obj in page]
    return render(request,'workbench/settings-list.html',shell(request,active='settings',title=title,code=code,
        rows=rows,page=page,q=q,tail=args.urlencode(),can_add=bool(fields and permitted(request.user,code,'add') and (code!='site' or not model.objects.exists()))))


def linked_rows(code,obj):
    links=[]
    if code=='section':links=[('步骤里的条目','block','section',obj.pk)]
    elif code=='notice':links=[('分条信息','fact','notice',obj.pk),('学院与级别','notice-tag','notice',obj.pk)]
    return [{'title':title,'list':reverse('maintenance:list',args=[c])+'?'+urlencode({key:pk}),
             'new':reverse('maintenance:new',args=[c])+'?'+urlencode({key:pk})} for title,c,key,pk in links]


def has_dependents(obj):
    # Never cascade a delete. Parents are hidden instead; support rows can be restored individually.
    return any(getattr(obj,relation.get_accessor_name()).exists()
               for relation in obj._meta.related_objects if relation.one_to_many or relation.many_to_many)


@secure
def editor(request,code,pk=None):
    model,title,fields,_,filters=config(code)
    creating=pk is None
    obj=model() if creating else get_object_or_404(model,pk=pk)
    readonly=code in READONLY or not permitted(request.user,code,'add' if creating else 'change')
    if creating and (readonly or code=='site' and model.objects.exists()):raise PermissionDenied
    if code in AUTH and not request.user.is_superuser:raise PermissionDenied
    if creating and model._meta.pk.get_internal_type()=='CharField':obj.pk='manual-'+uuid4().hex[:24]
    if creating and code=='site':obj.pk=1
    initial={key:request.GET[key] for key in filters if key in request.GET and key!='status'}
    before=None if creating else row_snapshot(obj)
    token=signing.dumps({'code':code,'pk':str(pk),'hash':audit.content_hash(before or {})},salt='maintenance')
    cls=form_class(code) if not readonly else None
    form=cls(request.POST or None,instance=obj,initial=initial) if cls else None
    if code=='user' and creating:
        class NewUser(UserCreationForm):
            class Meta(UserCreationForm.Meta):fields=('username','email','is_active','is_staff')
        form=NewUser(request.POST or None)
    status=200
    if request.method=='POST':
        if readonly:raise PermissionDenied
        if form.is_valid():
            try:
                with transaction.atomic():
                    if not creating:
                        obj=model.objects.select_for_update().get(pk=pk)
                        stamp=signing.loads(request.POST.get('baseline',''),salt='maintenance',max_age=86400)
                        if stamp!={'code':code,'pk':str(pk),'hash':audit.content_hash(row_snapshot(obj))}:
                            raise ValueError('内容已被另一个窗口修改，请重新打开核对。')
                    if code=='user' and not creating and str(pk)==str(request.user.pk):
                        if not all(form.cleaned_data.get(k) for k in ('is_active','is_staff','is_superuser')):
                            raise ValueError('不能停用或降低当前登录账号的权限。')
                    if creating:
                        if code=='notice-tag':form.instance.kind=form.cleaned_data['taxonomy'].kind
                        saved=form.save()
                    else:
                        # Write only form fields onto the locked row. In particular, an account
                        # profile save must never replace a concurrently changed password hash.
                        for key in fields:
                            field=model._meta.get_field(key)
                            if not field.many_to_many:
                                value=form.cleaned_data[key]
                                setattr(obj,field.attname,value.pk if field.many_to_one and value is not None else value)
                        if code=='notice-tag':obj.kind=form.cleaned_data['taxonomy'].kind
                        form.instance=obj;form.save(commit=False)
                        obj.save();form.save_m2m();saved=obj
                    refresh(saved)
                    record(code,saved.pk,before,row_snapshot(saved),request.user,'create' if creating else 'update')
                messages.success(request,'已保存，修改记录已保留。')
                return redirect('maintenance:edit',code=code,pk=saved.pk)
            except (ValueError,IntegrityError,signing.BadSignature) as exc:
                form.add_error(None,'信息冲突，请核对唯一名称、链接和关联内容。' if isinstance(exc,IntegrityError) else str(exc));status=409
    display=[]
    if readonly:
        for field in model._meta.concrete_fields:
            if field.name in ('password','snapshot'):continue
            value=getattr(obj,field.attname)
            display.append((field.verbose_name,json.dumps(value,ensure_ascii=False,indent=2) if isinstance(value,(dict,list)) else value))
    removable=(not creating and not readonly and code not in {'user','site','notice','group'}
               and permitted(request.user,code,'delete') and not has_dependents(obj))
    return render(request,'workbench/settings-edit.html',shell(request,active='settings',title=title,code=code,
        obj=obj,form=form,creating=creating,readonly=readonly,display=display,baseline=token,removable=removable,
        links=linked_rows(code,obj) if not creating else [],object_label=label(obj) if not creating else '新增'+title),status=status)


@secure
def remove(request,code,pk):
    if request.method!='POST':raise Http404
    if code in READONLY|{'user','site','notice','group'} or not permitted(request.user,code,'delete'):raise PermissionDenied
    with transaction.atomic():
        obj=get_object_or_404(config(code)[0].objects.select_for_update(),pk=pk)
        before=row_snapshot(obj)
        stamp=signing.loads(request.POST.get('baseline',''),salt='maintenance',max_age=86400)
        if stamp!={'code':code,'pk':str(pk),'hash':audit.content_hash(before)} or has_dependents(obj):raise PermissionDenied
        obj.delete()
        refresh(obj)
        record(code,pk,before,None,request.user,'delete')
    messages.success(request,'已移除这条内容，可在修改记录恢复。')
    return redirect('maintenance:list',code=code)


def restore_allowed(user,payload):
    code=payload.get('maintenance')
    if code not in REGISTRY or code in READONLY|{'user'} or not permitted(user,code,'change'):return False
    obj=config(code)[0].objects.filter(pk=payload['id']).first()
    # New rows are not silently deleted on rollback. Hide public content through its editor.
    if payload.get('before') is None:return False
    return row_snapshot(obj)==payload.get('after') if obj else payload.get('after') is None and permitted(user,code,'add')


@transaction.atomic
def restore(revision,user):
    payload=json.loads(gzip.decompress(revision.snapshot))
    code=payload['maintenance'];model=config(code)[0]
    model.objects.select_for_update().filter(pk=payload['id']).first()
    if not restore_allowed(user,payload):raise PermissionDenied
    before=payload['before'];obj=model.objects.filter(pk=payload['id']).first()
    old=row_snapshot(obj) if obj else None
    if obj is None:obj=model(pk=payload['id'])
    m2m={}
    for key,value in before.items():
        field=model._meta.get_field(key)
        if field.many_to_many:m2m[key]=value
        else:setattr(obj,field.attname,field.target_field.to_python(value) if field.many_to_one else field.to_python(value))
    obj.full_clean(exclude=list(m2m));obj.save()
    for key,values in m2m.items():getattr(obj,key).set(values)
    refresh(obj);record(code,obj.pk,old,row_snapshot(obj),user,'restore')


@secure
def password(request,pk):
    if not request.user.is_superuser:raise PermissionDenied
    obj=get_object_or_404(get_user_model(),pk=pk)
    form=AdminPasswordChangeForm(obj,request.POST or None)
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            form.save()
            # Record the action, never the password or its hash.
            record('user',obj.pk,{'password_updated':False},{'password_updated':True},request.user)
        if obj.pk==request.user.pk:update_session_auth_hash(request,obj)
        messages.success(request,'密码已更新。')
        return redirect('maintenance:edit',code='user',pk=pk)
    return render(request,'workbench/settings-edit.html',shell(request,active='settings',title='设置密码',
        form=form,obj=obj,code='user',object_label='为 '+obj.username+' 设置密码',password_form=True))


urlpatterns=[path('',index,name='home'),path('password/<str:pk>/',password,name='password'),
 path('<str:code>/',listing,name='list'),path('<str:code>/new/',editor,name='new'),
 path('<str:code>/<str:pk>/remove/',remove,name='remove'),path('<str:code>/<str:pk>/',editor,name='edit')]


def legacy(request,old_path=''):
    """Old bookmarks open the new screens; the old writable admin is no longer routed."""
    if request.method!='GET':
        from django.http import HttpResponseNotAllowed
        return HttpResponseNotAllowed(['GET'])
    parts=old_path.strip('/').split('/')
    if parts[0]=='login':return redirect('workbench:login')
    names={'activity':'activity','guide':'guide','campusservice':'service','notice':'notice'}
    if len(parts)>1 and parts[0]=='catalog' and parts[1] in names:
        kind=names[parts[1]]
        if len(parts)>2 and parts[2]=='add':return redirect('workbench:create',kind=kind)
        if len(parts)>3 and parts[3]=='change':return redirect('workbench:edit',kind=kind,pk=parts[2])
        if kind!='notice':return redirect('workbench:list',kind=kind)
        return redirect('maintenance:list',code='notice')
    by_model={config(code)[0]._meta.model_name:code for code in REGISTRY}
    if len(parts)>1 and parts[1] in by_model:
        code=by_model[parts[1]]
        if len(parts)>2 and parts[2]=='add':return redirect('maintenance:new',code=code)
        if len(parts)>3 and parts[3]=='change':return redirect('maintenance:edit',code=code,pk=parts[2])
        return redirect('maintenance:list',code=code)
    return redirect('workbench:home')
