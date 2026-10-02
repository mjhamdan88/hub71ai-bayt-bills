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
from .models import Bill, Budget, Payment, Message

@transaction.atomic
def seed(user):
    User.objects.select_for_update().get(pk=user.pk)
    if Bill.objects.filter(owner=user).exists(): return
    today = timezone.localdate()
    for merchant, category, amount in [('Bright Energy','Utilities',84),('Clear Water','Utilities',36),('HomeLink Internet','Internet',59),('Nest Rentals','Housing',1200),('StreamBox','Subscriptions',15)]:
        Budget.objects.get_or_create(owner=user, category=category, defaults={'limit': {'Utilities':180,'Internet':80,'Housing':1300,'Subscriptions':40}[category]})
        for month in range(4):
            Bill.objects.create(owner=user,merchant=merchant,category=category,amount=Decimal(amount) + (month*2 if category=='Utilities' else 0),due=today+timedelta(days=5-month*30),paid=month>0)
    Message.objects.create(owner=user,role='assistant',text='Welcome home. I prepared your private virtual household: 5 upcoming bills and 3 months of history. Review a bill below, set your category budgets, or ask me about your spending. All payments are simulations.')

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
    bills=Bill.objects.filter(owner=request.user)
    pending=bills.filter(paid=False).order_by('due','id')
    total=pending.aggregate(n=Sum('amount'))['n'] or 0
    history=[]
    for offset in (3,2,1):
        day=timezone.localdate()-timedelta(days=30*offset)+timedelta(days=5)
        history.append({'label':day.strftime('%b %Y'),'total':bills.filter(due=day).aggregate(n=Sum('amount'))['n'] or 0})
    budgets=list(Budget.objects.filter(owner=request.user).order_by('category'))
    for budget in budgets:
        budget.used=bills.filter(category=budget.category,due__gte=timezone.localdate().replace(day=1),due__lt=(timezone.localdate().replace(day=1)+timedelta(days=32)).replace(day=1)).aggregate(n=Sum('amount'))['n'] or 0
        budget.percent=min(100,int(budget.used/budget.limit*100)) if budget.limit else 100
    return render(request,'core/home.html',{'bills':pending,'all_bills':bills.order_by('-due'),'total':total,'forecast':sum(x['total'] for x in history)/3,'history':history,'budgets':budgets,'chat':Message.objects.filter(owner=request.user).order_by('id')[:100]})

@login_required(login_url='/login/')
@require_POST
@transaction.atomic
def pay(request,pk):
    User.objects.select_for_update().get(pk=request.user.pk)
    bill=get_object_or_404(Bill.objects.select_for_update(),pk=pk,owner=request.user)
    if not bill.paid:
        Payment.objects.create(bill=bill); bill.paid=True; bill.save(update_fields=['paid'])
        Message.objects.create(owner=request.user,role='assistant',text=f'Simulated payment complete: {bill.merchant}, ${bill.amount}. Your bill is marked paid. No money moved.')
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
        messages.error(request,'Enter a budget between $0 and $1,000,000.'); return redirect('/')
    item.autopay=request.POST.get('autopay')=='on'; item.save()
    messages.success(request,'Budget saved. Auto-pay only runs when you click Run demo auto-pay; no real money moves.')
    return redirect('/#budgets')

@login_required(login_url='/login/')
@require_POST
@transaction.atomic
def autopay(request):
    User.objects.select_for_update().get(pk=request.user.pk)
    today=timezone.localdate(); start=today.replace(day=1); end=(start+timedelta(days=32)).replace(day=1)
    count=0
    for item in Budget.objects.filter(owner=request.user,autopay=True):
        spent=Bill.objects.filter(owner=request.user,category=item.category,paid=True,due__gte=start,due__lt=end).aggregate(n=Sum('amount'))['n'] or Decimal(0)
        for bill in Bill.objects.select_for_update().filter(owner=request.user,category=item.category,paid=False,due__gte=start,due__lt=end).order_by('due','id'):
            if spent+bill.amount<=item.limit:
                Payment.objects.create(bill=bill,mode='auto_demo'); bill.paid=True; bill.save(); spent+=bill.amount; count+=1
    Message.objects.create(owner=request.user,role='assistant',text=f'Budget check complete. Simulated {count} payments within your enabled category limits for this month. No money moved.')
    return redirect('/')

@login_required(login_url='/login/')
@require_POST
def ai_respond(request):
    prompt=request.POST.get('prompt','').strip()[:2000]
    if not prompt: return redirect('/')
    if Message.objects.filter(owner=request.user,role='user',created__gte=timezone.now()-timedelta(minutes=1)).count()>=5:
        messages.error(request,'Please wait a minute before asking another question.'); return redirect('/')
    Message.objects.create(owner=request.user,role='user',text=prompt)
    context=list(Bill.objects.filter(owner=request.user).values('merchant','category','amount','due','paid'))
    budgets=list(Budget.objects.filter(owner=request.user).values('category','limit','autopay'))
    try:
        client=OpenAI(api_key=settings.OPENAI_API_KEY,base_url=settings.OPENAI_BASE_URL,timeout=35,max_retries=0)
        result=client.responses.create(model=settings.PORTACODE_LLM_MODEL,instructions='You are Bayt, a concise household finance assistant. Data is synthetic USD demo data. Only use the supplied user-scoped records. You cannot execute payments or change budgets: direct users to the visible buttons. Never claim actions happened. For the next-month forecast use the arithmetic mean of the three historical billing-period totals, not extrapolation. Forecasts are estimates, not guarantees. Answer in plain text under 150 words.',input=json.dumps({'question':prompt,'bills':context,'budgets':budgets},default=str),store=False)
        text=result.output_text or 'Please try your question again.'
    except OpenAIError:
        text='The live AI service is unavailable right now. Your bills and budgets are still available below; no changes were made.'
    Message.objects.create(owner=request.user,role='assistant',text=text)
    return redirect('/#conversation')

def health(request):
    with connection.cursor() as cursor: cursor.execute('SELECT 1')
    return JsonResponse({'status':'ok','app':'Bayt'})
