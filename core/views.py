import json
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.forms import UserCreationForm, AuthenticationForm
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db import transaction, connection
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_POST
from openai import OpenAI, OpenAIError
from .models import Bill, Budget, Payment, Message, Conversation, PaymentMethod
from .wallet import seed_wallet

@transaction.atomic
def seed(user):
    from datetime import date
    User.objects.select_for_update().get(pk=user.pk)
    for old,new in [('Utilities','TAQA home bill'),('Telecom','Internet & mobile')]:
        Bill.objects.filter(owner=user,source='samples_aed_v1',category=old).update(category=new)
        Budget.objects.filter(owner=user,category=old).update(category=new)
    if Bill.objects.filter(owner=user,source='samples_aed_v1').exists(): return
    # Archive the USD prototype without rewriting its payment history.
    Bill.objects.filter(owner=user,source='synthetic_demo').update(source='archived_usd')
    for category, limit in [('TAQA home bill','1400'),('Internet & mobile','600'),('Gas','100')]:
        Budget.objects.update_or_create(owner=user,category=category,defaults={'limit':Decimal(limit),'autopay':False})
    for month, power, telecom, gas, due_day in [(7,'1453.69','524.39','64.67',29),(8,'1364.76','524.20','64.67',27),(9,'1534.71','524.20','64.14',29)]:
        for merchant, category, amount, due in [('TAQA','TAQA home bill',power,date(2026,month,due_day)),('e&','Internet & mobile',telecom,date(2026,month+1,15)),('Gas supplier','Gas',gas,date(2026,month,28))]:
            Bill.objects.create(owner=user,merchant=merchant,category=category,amount=Decimal(amount),currency='AED',period=date(2026,month,1),due=due,paid=month<9,source='samples_aed_v1')
    Message.objects.create(owner=user,role='assistant',text='Your AED sample household is ready. Amounts match the supplied July–September 2026 bills. July and August are marked paid for the demo; September is awaiting simulated payment. Generated documents use your name, not the original personal details. Previous USD prototype records are archived, not converted.')


def auth(request):
    signup=request.GET.get('mode')=='signup'
    form=(UserCreationForm if signup else AuthenticationForm)(data=request.POST or None)
    if request.method=='POST' and form.is_valid():
        user=form.save() if signup else form.get_user()
        if signup:
            user.first_name=request.POST.get('name','').strip()[:150]; user.save()
        login(request,user); seed(user); return redirect('/')
    return render(request,'core/auth.html',{'form':form,'signup':signup})

@require_POST
def signout(request):
    logout(request); return redirect('/')

def home(request):
    if not request.user.is_authenticated: return redirect('/login/?mode=signup')
    seed(request.user)
    seed_wallet(request.user)
    bills=Bill.objects.filter(owner=request.user,currency="AED",source="samples_aed_v1")
    pending=bills.filter(paid=False).order_by('due','id')
    total=pending.aggregate(n=Sum('amount'))['n'] or 0
    from datetime import date
    history=[{'label':date(2026,m,1).strftime('%b %Y'),'total':bills.filter(period=date(2026,m,1)).aggregate(n=Sum('amount'))['n'] or Decimal(0)} for m in (7,8,9)]
    budgets=list(Budget.objects.filter(owner=request.user,category__in=['TAQA home bill','Internet & mobile','Gas']).order_by('id'))
    for budget in budgets:
        budget.used=bills.filter(category=budget.category,period=date(2026,9,1)).aggregate(n=Sum('amount'))['n'] or Decimal(0)
        budget.percent=round(budget.used/budget.limit*100) if budget.limit else (100 if budget.used else 0)
        budget.bar=min(100,budget.percent)
        budget.over=budget.used>budget.limit
        budget.excess=budget.used-budget.limit
        budget.pending=list(bills.filter(category=budget.category,paid=False))
        budget.months=[bills.filter(category=budget.category,period=date(2026,m,1)).aggregate(n=Sum('amount'))['n'] or Decimal(0) for m in (7,8,9)]
        budget.chart_points=[{'x':80+i*250,'y':370-float(value)/1800*330,'label_y':356-float(value)/1800*330,'amount':f'{value:,.2f}'} for i,value in enumerate(budget.months)]
        budget.points=' '.join(f'{point["x"]},{point["y"]:.2f}' for point in budget.chart_points)
        peak=max(budget.months) or Decimal(1)
        budget.chart_max=peak*Decimal('1.2')
        budget.detail_points=' '.join(f'{70+i*210},{108-float(value/budget.chart_max)*80:.2f}' for i,value in enumerate(budget.months))
        budget.color=['#286452','#b58333','#6a74ae'][budgets.index(budget)%3]
        budget.documents=list(bills.filter(category=budget.category).order_by('period'))
    response=render(request,'core/overview_data.html' if request.GET.get('fragment')=='overview' else 'core/home.html',{'payment_methods':PaymentMethod.objects.filter(owner=request.user,active=True),'bills':pending,'all_bills':bills.order_by('-due'),'total':total,'forecast':sum(x['total'] for x in history)/3,'history':history,'budgets':budgets,'category_total':sum(b.used for b in budgets),'over_count':sum(b.over for b in budgets),'chat':Message.objects.filter(owner=request.user,created__gte=Message.objects.filter(owner=request.user,text__startswith='Your AED sample household').latest('id').created).order_by('id')[:100]})
    response['Cache-Control']='private, no-store'
    return response

@login_required(login_url='/login/')
@require_POST
@transaction.atomic
def pay(request,pk):
    User.objects.select_for_update().get(pk=request.user.pk)
    bill=get_object_or_404(Bill.objects.select_for_update(),pk=pk,owner=request.user,currency="AED",source="samples_aed_v1")
    if not bill.paid:
        method=Budget.objects.filter(owner=request.user,category=bill.category).first().payment_method
        if not method or not method.active or method.owner_id!=request.user.pk:
            messages.error(request,'Select a payment method for this category first.'); return redirect('/')
        Payment.objects.create(bill=bill,payment_method=method); bill.paid=True; bill.save(update_fields=['paid'])
        Message.objects.create(owner=request.user,role='assistant',text=f'Simulated payment complete: {bill.merchant}, AED {bill.amount}. Your bill is marked paid. No money moved.')
    return redirect('/')

@login_required(login_url='/login/')
@require_POST
@transaction.atomic
def budget(request,pk):
    User.objects.select_for_update().get(pk=request.user.pk)
    item=get_object_or_404(Budget,pk=pk,owner=request.user)
    try:
        amount=Decimal(request.POST.get('limit',''))
        if not amount.is_finite() or amount<0 or amount>1000000: raise ValueError()
        item.limit=amount.quantize(Decimal('.01'))
    except (InvalidOperation,ValueError):
        messages.error(request,'Enter a budget between AED 0 and AED 1,000,000.'); return redirect('/')
    item.save()
    messages.success(request,'Budget saved. No payments were made.')
    return redirect('/')

@login_required(login_url='/login/')
@require_POST
@transaction.atomic
def autopay(request):
    User.objects.select_for_update().get(pk=request.user.pk)
    from datetime import date
    start=date(2026,9,1)
    count=0
    for item in Budget.objects.filter(owner=request.user,autopay=True):
        spent=Bill.objects.filter(owner=request.user,category=item.category,paid=True,period=start,currency="AED",source="samples_aed_v1").aggregate(n=Sum('amount'))['n'] or Decimal(0)
        for bill in Bill.objects.select_for_update().filter(owner=request.user,category=item.category,paid=False,period=start,currency="AED",source="samples_aed_v1").order_by('due','id'):
            if spent+bill.amount<=item.limit:
                Payment.objects.create(bill=bill,mode='auto_demo'); bill.paid=True; bill.save(); spent+=bill.amount; count+=1
    Message.objects.create(owner=request.user,role='assistant',text=f'Budget check complete. Simulated {count} payments within your enabled category limits for September 2026. No money moved.')
    return redirect('/')

@login_required(login_url='/login/')
@require_POST
def ai_respond(request):
    prompt=request.POST.get('prompt',request.POST.get('text','')).strip()[:2000]
    if request.FILES: return JsonResponse({'error':'This finance chat accepts text only.'},status=400)
    if not prompt: return JsonResponse({'error':'Enter a question.'},status=400)
    if Message.objects.filter(owner=request.user,role='user',created__gte=timezone.now()-timedelta(minutes=1)).count()>=5:
        return JsonResponse({'error':'Please wait a minute before asking another question.'},status=429)
    user_message=Message.objects.create(owner=request.user,role='user',text=prompt)
    context=list(Bill.objects.filter(owner=request.user,currency='AED',source='samples_aed_v1').values('merchant','category','amount','currency','period','due','paid'))
    budgets=list(Budget.objects.filter(owner=request.user,category__in=['TAQA home bill','Internet & mobile','Gas']).values('category','limit','autopay'))
    try:
        client=OpenAI(api_key=settings.OPENAI_API_KEY,base_url=settings.OPENAI_BASE_URL,timeout=35,max_retries=0)
        result=client.responses.create(model=settings.PORTACODE_LLM_MODEL,instructions='You are Bayt, a concise household finance assistant. Data is sanitized AED sample data from July, August and September 2026. All amounts are AED, never dollars. September is the active demo period. The exact three-month total is AED 6119.43 and arithmetic-mean forecast is AED 2039.81. Do not invent conversions or recalculate a different forecast. Only use the supplied user-scoped records. You cannot execute payments or change budgets: direct users to the visible buttons. Never claim actions happened. For the next-month forecast use the arithmetic mean of the three historical billing-period totals, not extrapolation. Forecasts are estimates, not guarantees. Answer in plain text under 150 words.',input=json.dumps({'question':prompt,'bills':context,'budgets':budgets},default=str),store=False)
        text=result.output_text or 'Please try your question again.'
    except OpenAIError:
        text='The live AI service is unavailable right now. Your bills and budgets are still available below; no changes were made.'
    Message.objects.create(owner=request.user,role='assistant',text=text)
    if request.path.startswith('/finance-chat/'):
        return JsonResponse({'message':chat_message(user_message)})
    return redirect('/#conversation')

def health(request):
    with connection.cursor() as cursor: cursor.execute('SELECT 1')
    return JsonResponse({'status':'ok','app':'Bayt'})

@login_required(login_url='/login/')
def document(request,pk):
    bill=get_object_or_404(Bill,pk=pk,owner=request.user,currency='AED',source='samples_aed_v1')
    response=render(request,'core/document.html',{'bill':bill})
    response['Cache-Control']='private, no-store'
    if request.GET.get('download'):
        response['Content-Disposition']=f'attachment; filename="Bayt-bill-{bill.pk}.html"'
    return response


def chat_message(m):
    metadata=dict(m.metadata)
    if metadata.get('action_id'):
        from .models import ActionRequest
        action=ActionRequest.objects.filter(pk=metadata['action_id'],owner=m.owner).first()
        if action:
            pending=action.status=='pending' and action.created >= timezone.now()-timedelta(minutes=15)
            metadata['interactive_buttons']=[[{'text':'Confirm change' if pending else action.status.title() if action.status!='pending' else 'Expired','type':'finance_action','action_id':action.pk,'decision':'confirm','disabled':not pending}, {'text':'Cancel','type':'finance_action','action_id':action.pk,'decision':'cancel','style':'secondary','disabled':not pending}]]
    return {'id':str(m.pk),'text':m.text,'media_type':'text','is_outgoing':m.role!='user','sender_name':'Bayt' if m.role!='user' else 'You','timestamp':m.created.isoformat(),**metadata}

@login_required(login_url='/login/')
def chat_messages(request):
    seed(request.user)
    marker=Message.objects.filter(owner=request.user,text__startswith='Your AED sample household').order_by('id').first()
    cid=request.GET.get('chat_id','')
    if not cid.isdigit(): return JsonResponse({'messages':[],'has_more':False})
    conversation=get_object_or_404(Conversation,pk=cid,owner=request.user)
    qs=Message.objects.filter(owner=request.user,conversation=conversation).exclude(text__startswith='Your AED sample household')
    if marker: qs=qs.filter(id__gte=marker.pk)
    try:
        if request.GET.get('after'): qs=qs.filter(id__gt=int(request.GET['after']))
        if request.GET.get('before'): qs=qs.filter(id__lt=int(request.GET['before']))
    except ValueError: return JsonResponse({'error':'Invalid cursor'},status=400)
    rows=list(qs.order_by('-id')[:50]); rows.reverse()
    return JsonResponse({'messages':[chat_message(m) for m in rows],'has_more':False})

@login_required(login_url='/login/')
def conversations(request):
    with transaction.atomic():
        User.objects.select_for_update().get(pk=request.user.pk)
        old=Message.objects.filter(owner=request.user,conversation__isnull=True).exclude(text__startswith='Your AED sample household')
        if old.exists():
            chat=Conversation.objects.create(owner=request.user,title='Previous conversation')
            old.update(conversation=chat)
    return JsonResponse({'chats':[{'id':str(c.pk),'name':c.title,'last_message':chat_message(c.message_set.order_by('-id').first()) if c.message_set.exists() else None,'updated_at':c.created.isoformat()} for c in Conversation.objects.filter(owner=request.user).order_by('-id')]})

@login_required(login_url='/login/')
def profile(request):
    if request.method=='POST':
        request.user.first_name=request.POST.get('first_name','').strip()[:150]
        request.user.last_name=request.POST.get('last_name','').strip()[:150]
        request.user.save(update_fields=['first_name','last_name'])
        messages.success(request,'Profile updated.')
        return redirect('/profile/')
    return render(request,'core/profile.html')

@login_required(login_url='/login/')
def payment_methods(request):
    seed_wallet(request.user)
    return render(request,'core/payment_methods.html',{'cards':PaymentMethod.objects.filter(owner=request.user,active=True)})
