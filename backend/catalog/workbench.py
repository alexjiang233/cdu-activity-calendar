"""A staff-only editorial workspace over the existing audited content services."""
import gzip
import json
from functools import wraps
from uuid import uuid4
from urllib.parse import urlencode

from django import forms
from django.contrib import messages
from django.contrib.admin.forms import AdminAuthenticationForm
from django.contrib.auth.views import LoginView, LogoutView
from django.core import signing
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Exists, OuterRef, Q
from django.db.models import Model
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache

from . import audit, drafts, services
from .models import (Activity, CampusService, DraftChange, Guide, Notice, Revision,
                     SiteMeta, Taxonomy)

KINDS = {'activity': (Activity, '活动内容', 'activities'),
         'guide': (Guide, '校园指南', 'guides'),
         'service': (CampusService, '校园查询', 'services'),
         'notice': (Notice, '通知版本', 'activities')}
LABELS = {'title': '标题', 'name': '服务名称', 'summary': '卡片摘要', 'category': '类别',
          'tags': '标签', 'editorial_note': '补充说明', 'featured': '允许推荐',
          'spotlight': '精选活动', 'visibility': '公开状态', 'position': '显示顺序',
          'subtitle': '副标题', 'scope': '适用范围', 'caution': '提醒', 'source_note': '资料说明',
          'related_service': '关联服务', 'description': '说明', 'owner': '负责单位',
          'phone': '公开电话', 'url': '官方入口', 'location': '地点', 'open_hours': '服务时间',
          'note': '使用说明', 'year': '所属年份', 'published': '公告日期', 'deadline': '报名／提交截止',
          'deadline_kind': '截止类型', 'stage_start': '活动开始', 'stage_end': '活动结束',
          'audience': '参与对象', 'conflict': '原文存在冲突', 'facts': '分条信息',
          'sections': '指南步骤', 'faqs': '常见问题'}


def guard(kind=None, change=False):
    def decorate(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect(reverse('workbench:login') + '?' + urlencode({'next': request.get_full_path()}))
            if not request.user.is_active or not request.user.is_staff:
                raise PermissionDenied
            actual = kind or kwargs.get('kind')
            if actual:
                if actual not in KINDS:
                    raise Http404
                model = KINDS[actual][0]
                prefix = 'change' if change else 'view'
                if not request.user.has_perm(f'catalog.{prefix}_{model._meta.model_name}'):
                    raise PermissionDenied
            return view(request, *args, **kwargs)
        return never_cache(wrapped)
    return decorate


def shell(request, **ctx):
    ctx['nav'] = [(code, label, reverse('workbench:list', args=[kind]))
                  for kind, (model, label, code) in KINDS.items()
                  if kind != 'notice' and request.user.has_perm(f'catalog.view_{model._meta.model_name}')]
    ctx['pending_total'] = DraftChange.objects.filter(status='draft').count()
    return ctx


class Login(LoginView):
    template_name = 'workbench/login.html'
    authentication_form = AdminAuthenticationForm
    redirect_authenticated_user = False

    def get_success_url(self):
        return self.get_redirect_url() or reverse('workbench:home')


@guard()
def home(request):
    stats = [(label, model.objects.count(), reverse('workbench:list', args=[kind]))
             for kind, (model, label, code) in KINDS.items()
             if kind != 'notice' and request.user.has_perm(f'catalog.view_{model._meta.model_name}')]
    recent = Activity.objects.select_related('category').order_by('-updated_at')[:5] if request.user.has_perm('catalog.view_activity') else []
    pending = [d for d in DraftChange.objects.filter(status='draft').select_related('author')
               if d.entity_kind in KINDS and request.user.has_perm(
                   f'catalog.change_{KINDS[d.entity_kind][0]._meta.model_name}')][:5]
    for d in pending:
        d.display_title=d.payload.get('title') or d.payload.get('name') or d.get_entity_kind_display()
    return render(request, 'workbench/home.html', shell(request, active='home', stats=stats,
                  recent=recent, pending=pending, title='内容工作台'))


@guard()
def listing(request, kind):
    if kind == 'notice':
        raise Http404
    model, label, active = KINDS[kind]
    q, state = request.GET.get('q', '').strip()[:120], request.GET.get('state', '')
    query = model.objects.all()
    if kind == 'activity':
        query = query.select_related('category').annotate(notice_total=Count('notices', distinct=True))
    pending = DraftChange.objects.filter(entity_kind=kind, entity_id=OuterRef('pk'), status='draft')
    query = query.annotate(has_draft=Exists(pending))
    if q:
        field = 'name' if kind == 'service' else 'title'
        query = query.filter(Q(**{f'{field}__icontains': q}) | Q(pk__icontains=q))
    if state in ('public', 'hidden'):
        query = query.filter(visibility=state)
    if state == 'draft':
        query = query.filter(has_draft=True)
    category = request.GET.get('category', '')
    if category and kind == 'activity':
        query = query.filter(category_id=category) if category.isdigit() else query.none()
    query = query.order_by('-updated_at', 'pk')
    page = Paginator(query, 16).get_page(request.GET.get('page'))
    params = request.GET.copy(); params.pop('page', None)
    rows = [{'obj': obj, 'name': str(obj), 'edit_url': reverse('workbench:edit', args=[kind, obj.pk])}
            for obj in page]
    return render(request, 'workbench/list.html', shell(request, active=active, title=label,
                  kind=kind, rows=rows, page=page, q=q, state=state, category=category,
                  categories=Taxonomy.objects.filter(kind='category'),
                  query_tail=params.urlencode(), can_change=request.user.has_perm(
                      f'catalog.change_{model._meta.model_name}'),
                  total=model.objects.count(), public_count=model.objects.filter(visibility='public').count()))


class CategoryChoice(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.label


class ContentForm(forms.ModelForm):
    class Meta:
        model = Activity
        fields = ('title', 'category', 'summary', 'tags', 'editorial_note',
                  'featured', 'spotlight', 'position', 'visibility', 'kind', 'split_by_college', 'material_ids')
        widgets = {'summary': forms.Textarea(attrs={'rows': 3}),
                   'editorial_note': forms.Textarea(attrs={'rows': 3})}
    tags = forms.CharField(label='标签', required=False, help_text='用逗号分开，例如：创作、团队合作')
    category = CategoryChoice(queryset=Taxonomy.objects.filter(kind='category'), required=False, label='活动类别')
    material_ids = forms.JSONField(label='关联资料编号',required=False,help_text='兼容已有资料关联；日常维护无需修改。')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['category'].queryset = Taxonomy.objects.filter(kind='category')
        self.fields['category'].empty_label = '暂不分类'
        if not self.is_bound:
            value=self.initial.get('tags',self.instance.tags or [])
            self.initial['tags'] = '，'.join(value) if isinstance(value,list) else value
        self.fields['featured'].label = '允许推荐'
        self.fields['spotlight'].label = '设为精选'

    def clean_tags(self):
        return [x.strip() for x in self.cleaned_data['tags'].replace('，', ',').replace('、', ',').split(',') if x.strip()][:20]

    def clean_material_ids(self):
        value=self.cleaned_data['material_ids'] or []
        if not isinstance(value,list):raise forms.ValidationError('资料编号需填写为列表。')
        return value


class GuideForm(forms.ModelForm):
    tags=forms.CharField(label='标签',required=False,help_text='多个标签用逗号分开。')
    class Meta:
        model = Guide
        fields = ('title', 'subtitle', 'summary', 'scope', 'caution', 'source_note', 'category', 'visibility',
                  'number','icon','tags','position','related_service')
        widgets = {f: forms.Textarea(attrs={'rows': 2}) for f in ('summary', 'scope', 'caution', 'source_note')}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound:
            value=self.initial.get('tags',self.instance.tags or [])
            self.initial['tags']='，'.join(value) if isinstance(value,list) else value
        self.chapters = []
        if self.instance._state.adding:return
        for section in self.instance.sections.order_by('position', 'pk').prefetch_related('blocks'):
            name = f'section_{section.pk}'
            self.fields[name] = forms.CharField(label='步骤标题', max_length=120, initial=section.title)
            self.fields[name+'_position'] = forms.IntegerField(label='顺序', min_value=0, initial=section.position)
            blocks=[]
            for block in section.blocks.all():
                key=f'block_{block.pk}'
                self.fields[key] = forms.CharField(label='条目', initial=block.text, widget=forms.Textarea(attrs={'rows':2}), max_length=12000)
                blocks.append((block, key))
            self.chapters.append((section, name, blocks))
        self.questions=[]
        for faq in self.instance.faqs.order_by('position','pk'):
            q,a=f'faq_question_{faq.pk}',f'faq_answer_{faq.pk}'
            self.fields[q]=forms.CharField(label='问题',initial=faq.question,max_length=200)
            self.fields[a]=forms.CharField(label='回答',initial=faq.answer,widget=forms.Textarea(attrs={'rows':3}))
            self.questions.append((faq,q,a))

    def clean_tags(self):
        value=self.cleaned_data['tags'].strip()
        # Accept the old empty-list input without turning it into a visible label.
        return [] if value=='[]' else [x.strip() for x in value.replace('，',',').replace('、',',').split(',') if x.strip()]


class ServiceForm(forms.ModelForm):
    class Meta:
        model = CampusService
        fields = ('name', 'category', 'description', 'owner', 'phone', 'url', 'location', 'open_hours', 'note', 'visibility',
                  'position','source_url','source_label','source_date','checked_on','related_guide')
        widgets = {'description':forms.Textarea(attrs={'rows':3})}


class NoticeForm(forms.ModelForm):
    class Meta:
        model = Notice
        fields = ('activity','source','year', 'published', 'audience', 'deadline', 'deadline_kind', 'stage_start', 'stage_end', 'conflict','position','visibility')
        widgets = {'published':forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d'),
                   'stage_start':forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d'),
                   'stage_end':forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d'),
                   'audience':forms.Textarea(attrs={'rows':2}),
                   'deadline':forms.DateTimeInput(attrs={'type':'datetime-local'},format='%Y-%m-%dT%H:%M')}

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fact_rows=[]
        self.fields['deadline'].input_formats=['%Y-%m-%dT%H:%M','%Y-%m-%dT%H:%M:%S']
        self.fields['deadline_kind']=forms.ChoiceField(label='截止类型',required=False, choices=[
            ('','未分类'),('registration','报名截止'),('submission','作品提交截止'),('combined','报名及作品截止'),('notice','其他截止')])
        existing=self.initial.get('deadline_kind') or self.instance.deadline_kind
        if existing and existing not in dict(self.fields['deadline_kind'].choices):
            self.fields['deadline_kind'].choices += [(existing,'原有截止类型（保留）')]
        for fact in (self.instance.facts.order_by('position','pk') if not self.instance._state.adding else []):
            key=f'fact_{fact.pk}'
            self.fields[key]=forms.CharField(label=fact.label or '分条内容',initial=fact.value,
                                            widget=forms.Textarea(attrs={'rows':2}),max_length=16000)
            self.fact_rows.append((fact,key))


FORMS={'activity':ContentForm,'guide':GuideForm,'service':ServiceForm,'notice':NoticeForm}


def form_payload(form, kind, original):
    payload={}
    for key in form.Meta.fields:
        value=form.cleaned_data[key]
        payload[key]=value.pk if isinstance(value,Model) else audit._jsonable(value)
    if kind=='notice':
        payload['facts']=[{**row,'value':form.cleaned_data[f'fact_{row["id"]}']} for row in original['facts']]
    if kind=='guide':
        payload['sections']=[{**s,'title':form.cleaned_data[f'section_{s["id"]}'],
            'position':form.cleaned_data[f'section_{s["id"]}_position'],
            'blocks':[{**b,'text':form.cleaned_data[f'block_{b["id"]}']} for b in s['blocks']]}
            for s in original['sections']]
        payload['faqs']=[{**f,'question':form.cleaned_data[f'faq_question_{f["id"]}'],
                        'answer':form.cleaned_data[f'faq_answer_{f["id"]}']} for f in original['faqs']]
    return payload


@guard(change=True)
def edit(request, kind, pk):
    model,label,active=KINDS[kind]
    obj=get_object_or_404(model,pk=pk)
    original=audit.snapshot(kind,obj)
    latest=DraftChange.objects.filter(entity_kind=kind,entity_id=pk,status='draft').first()
    initial={**original,**(latest.payload if latest else {})}
    if kind=='notice':
        for key in ('published','deadline','stage_start','stage_end'):
            initial[key]=model._meta.get_field(key).to_python(initial.get(key))
    if kind=='activity':
        initial['tags']='，'.join(initial.get('tags') or [])
    form=FORMS[kind](request.POST or None,instance=obj,initial=initial)
    # ModelForms assign cleaned values to instance during validation; compare against a fresh row.
    token=signing.dumps({'id':pk,'kind':kind,'hash':audit.content_hash(original),
                         'draft':latest.pk if latest else None},salt='workbench-edit')
    status=200
    if request.method=='POST' and form.is_valid():
        try:
            stamp=signing.loads(request.POST.get('baseline',''),salt='workbench-edit',max_age=86400)
            with transaction.atomic():
                fresh=model.objects.select_for_update().get(pk=pk)
                current=audit.snapshot(kind,fresh)
                if stamp.get('id')!=pk or stamp.get('kind')!=kind or stamp.get('hash')!=audit.content_hash(current):
                    raise ValueError('这条内容刚刚发生了变化。请在新窗口重新打开核对，当前输入已保留。')
                if stamp.get('draft')!=(latest.pk if latest else None):
                    raise ValueError('这份草稿刚刚被其他窗口更新。请重新打开核对，当前输入已保留。')
                if latest and latest.payload.get('_base_hash') and latest.payload['_base_hash']!=audit.content_hash(current):
                    raise ValueError('这份草稿基于较早内容，请重新核对公开版本后再编辑。')
                payload=form_payload(form,kind,original)
                draft=drafts.save_draft(kind,pk,payload,note=request.POST.get('note','')[:200],author=request.user)
                DraftChange.objects.filter(entity_kind=kind,entity_id=pk,status='draft').exclude(pk=draft.pk).update(status='discarded')
                action=request.POST.get('action','save')
                if action=='publish':
                    drafts.publish(draft,actor=request.user)
                    messages.success(request,'已发布，前台内容已经更新。')
                else:
                    messages.success(request,'草稿已保存。公开页面保持原来的内容。')
            return redirect('workbench:edit',kind=kind,pk=pk)
        except (ValueError, signing.BadSignature) as exc:
            form.add_error(None,str(exc));status=409
    # Reopen nested draft values without exposing a JSON editor.
    if request.method!='POST' and latest:
        for section in initial.get('sections',[]):
            form.initial[f'section_{section["id"]}']=section['title']
            form.initial[f'section_{section["id"]}_position']=section['position']
            for block in section['blocks']:form.initial[f'block_{block["id"]}']=block['text']
        for fact in initial.get('facts',[]):form.initial[f'fact_{fact["id"]}']=fact['value']
        for faq in initial.get('faqs',[]):
            form.initial[f'faq_question_{faq["id"]}']=faq['question']
            form.initial[f'faq_answer_{faq["id"]}']=faq['answer']
    names=set(form.Meta.fields)
    fields=[form[key] for key in form.Meta.fields]
    chapters=[{'title':form[name],'order':form[name+'_position'],'blocks':[form[key] for block,key in blocks]}
              for section,name,blocks in getattr(form,'chapters',[])]
    facts=[{'field':form[key],'quote':fact.quote,'locator':fact.locator} for fact,key in getattr(form,'fact_rows',[])]
    questions=[{'question':form[q],'answer':form[a]} for faq,q,a in getattr(form,'questions',[])]
    if kind=='activity':
        # Staff must also see hidden, grouped and migrated source notices.
        notices=list(Notice.objects.filter(Q(activity=obj)|Q(display_activity=obj))
                     .select_related('source').order_by('-year','-published','position').distinct())
    else:notices=[]
    changes=Revision.objects.filter(changes__entity_kind=kind,changes__entity_id=pk).distinct()[:6]
    from .maintenance import linked_rows
    links=linked_rows('notice',obj) if kind=='notice' else []
    if kind=='guide':
        links=[{'title':label,'new':reverse('maintenance:new',args=[code])+'?'+urlencode({'guide':pk}),
                'list':reverse('maintenance:list',args=[code])+'?'+urlencode({'guide':pk})}
               for code,label in [('section','指南步骤'),('faq','常见问答'),('guide-source','资料来源')]]
    return render(request,'workbench/edit.html',shell(request,active=active,title=str(obj),kind=kind,obj=obj,links=links,
        form=form,fields=fields,chapters=chapters,facts=facts,questions=questions,baseline=token,original=original,
        latest=latest,notices=notices,changes=changes,label=label,
        editor_title=(obj.activity.title+' · '+str(obj.year or '年份未明')+' 年通知' if kind=='notice' else str(obj)),
        original_display={LABELS.get(k,k):v for k,v in original.items() if k in names}),status=status)


@guard()
def create(request,kind):
    model,label,active=KINDS[kind]
    if not request.user.has_perm(f'catalog.add_{model._meta.model_name}'):raise PermissionDenied
    obj=model(pk='manual-'+uuid4().hex[:24])
    if kind!='notice':obj.visibility='hidden'
    initial={'visibility':'hidden'} if kind!='notice' else {'activity':request.GET.get('activity')}
    form=FORMS[kind](request.POST or None,instance=obj,initial=initial)
    if kind!='notice':form.fields['visibility'].disabled=True
    if request.method=='POST' and form.is_valid():
        with transaction.atomic():
            saved=form.save(commit=False)
            if kind!='notice':saved.visibility='hidden'
            saved.save();form.save_m2m()
            if kind=='activity':
                from .indexing import refresh_activity
                refresh_activity(saved)
            elif kind=='notice':
                from .indexing import refresh_notice
                refresh_notice(saved)
            rev=audit.open_revision('手动新增：'+str(saved),'workbench',actor=request.user,
                payload={'kind':kind,'id':saved.pk,'before':None,'after':audit.snapshot(kind,saved)})
            audit.log_change(rev,kind,saved.pk,'create',None,audit.snapshot(kind,saved),actor=request.user)
            audit.publish_revision(rev)
        messages.success(request,'已添加。请补全内容后再设为公开。' if kind!='notice' else '通知已添加，可继续添加报名、材料等条目。')
        return redirect('workbench:edit',kind=kind,pk=saved.pk)
    return render(request,'workbench/create.html',shell(request,title='新增'+label,active=active,form=form,kind=kind,label=label))


@require_POST
@guard(change=True)
def discard_draft(request,kind,pk):
    with transaction.atomic():
        obj=get_object_or_404(KINDS[kind][0].objects.select_for_update(),pk=pk)
        DraftChange.objects.filter(entity_kind=kind,entity_id=pk,status='draft').update(status='discarded')
        if hasattr(obj,'draft'):
            obj.draft=None
            obj.save(update_fields=['draft'])
    messages.success(request,'已放弃未发布的草稿，公开内容保持不变。')
    return redirect('workbench:edit',kind=kind,pk=pk)


@require_POST
@guard(change=True)
def bulk(request,kind):
    if kind=='notice':raise Http404
    model=KINDS[kind][0]
    action=request.POST.get('action')
    if action=='extra':action=request.POST.get('extra_action')
    updates={'hide':{'visibility':'hidden'},'show':{'visibility':'public'}}
    if kind=='activity':updates.update({'feature':{'featured':True},'unfeature':{'featured':False},
                                       'spotlight':{'spotlight':True},'unspotlight':{'spotlight':False}})
    if action not in updates:raise Http404
    ids=request.POST.getlist('selected')[:100]
    with transaction.atomic():
        rows=list(model.objects.select_for_update().filter(pk__in=ids))
        for obj in rows:
            audit.apply_updates(kind,obj,updates[action],reason='工作台批量调整展示',origin='workbench',actor=request.user)
    messages.success(request,f'已处理 {len(rows)} 条内容，可在修改记录查看。')
    return redirect('workbench:list',kind=kind)


@guard()
def history(request):
    if not request.user.has_perm('catalog.view_revision'):raise PermissionDenied
    page=Paginator(Revision.objects.select_related('batch').order_by('-created_at'),20).get_page(request.GET.get('page'))
    return render(request,'workbench/history.html',shell(request,active='history',title='修改记录',page=page))


@guard()
def revision(request,pk):
    if not request.user.has_perm('catalog.view_revision'):raise PermissionDenied
    obj=get_object_or_404(Revision,pk=pk)
    try:payload=json.loads(gzip.decompress(obj.snapshot)) if obj.snapshot else {}
    except (ValueError,OSError):payload={}
    before,after=payload.get('before') or {},payload.get('after') or {}
    if payload.get('maintenance'):
        from . import maintenance
        can_restore=maintenance.restore_allowed(request.user,payload)
        model=maintenance.config(payload['maintenance'])[0]
        labels={f.name:str(f.verbose_name) for f in model._meta.get_fields() if hasattr(f,'verbose_name')}
        diffs=[{'label':labels.get(key,key),'before':before.get(key),'after':after.get(key)}
               for key in after.keys()|before.keys() if before.get(key)!=after.get(key)]
        if request.method=='POST':
            if not can_restore:raise PermissionDenied
            maintenance.restore(obj,request.user)
            messages.success(request,'已恢复这次修改，并保留了恢复记录。')
            return redirect('workbench:history')
        return render(request,'workbench/revision.html',shell(request,active='history',title='查看修改',revision=obj,diffs=diffs,can_restore=can_restore))
    diffs=[{'label':LABELS.get(key,key),'before':before.get(key),'after':after.get(key)}
           for key in after.keys()|before.keys() if before.get(key)!=after.get(key)]
    can_restore=False
    kind=payload.get('kind')
    if kind in KINDS and before and payload.get('id'):
        model=KINDS[kind][0]
        entity=model.objects.filter(pk=payload['id']).first()
        can_restore=bool(entity and request.user.has_perm(f'catalog.change_{model._meta.model_name}')
                         and audit.matches_snapshot(kind,entity,after))
    if request.method=='POST':
        with transaction.atomic():
            if not can_restore:raise PermissionDenied
            entity=model.objects.select_for_update().get(pk=payload['id'])
            if not audit.matches_snapshot(kind,entity,after):
                raise PermissionDenied('内容又有了新的修改，请重新核对。')
            audit.restore(obj,actor=request.user)
        messages.success(request,'已撤回这次修改，并保留了新的恢复记录。')
        return redirect('workbench:history')
    return render(request,'workbench/revision.html',shell(request,active='history',title='查看修改',revision=obj,
                  diffs=diffs,can_restore=can_restore))


urlpatterns=[path('',home,name='home'),path('version/',lambda request:JsonResponse({'app':'campus-workbench-2'}),name='version'),path('login/',Login.as_view(),name='login'),
    path('logout/',LogoutView.as_view(next_page='/manage/login/'),name='logout'),
    path('history/',history,name='history'),path('history/<str:pk>/',revision,name='revision'),
    path('new/<str:kind>/',create,name='create'),
    path('<str:kind>/',listing,name='list'),path('<str:kind>/bulk/',bulk,name='bulk'),
    path('<str:kind>/<str:pk>/discard/',discard_draft,name='discard'),
    path('<str:kind>/<str:pk>/',edit,name='edit')]
