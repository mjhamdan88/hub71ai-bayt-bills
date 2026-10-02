from decimal import Decimal, InvalidOperation
from datetime import timedelta
from django.db import transaction
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.http import JsonResponse
from .models import Wallet, PaymentMethod, Budget, Bill, Payment, ActionRequest

@transaction.atomic
def seed_wallet(user):
    User.objects.select_for_update().get(pk=user.pk)
    _,created=Wallet.objects.get_or_create(owner=user)
    if created:
        first=PaymentMethod.objects.create(owner=user,bank='FAB',network='Visa',last4='4242')
        PaymentMethod.objects.create(owner=user,bank='ADCB',network='Mastercard',last4='5556')
        Budget.objects.filter(owner=user,payment_method__isnull=True).update(payment_method=first)

@login_required
@require_POST
@transaction.atomic
def add(request):
    seed_wallet(request.user)
    bank=request.POST.get('bank','').strip()
    cardholder=request.POST.get('cardholder','').strip()
    network=request.POST.get('network','')
    last4=request.POST.get('last4','').strip()
    expiry=request.POST.get('expiry','').strip()
    import re
    if (not bank or len(bank)>80 or not cardholder or len(cardholder)>100
            or network not in ['Visa','Mastercard','American Express','Discover','UnionPay','Other']
            or not re.fullmatch(r'[0-9]{4}',last4)
            or not re.fullmatch(r'[0-9]{4}-(0[1-9]|1[0-2])',expiry)):
        messages.error(request,'Enter the card details in the fields below.')
        return render(request,'core/payment_methods.html',{
            'cards':PaymentMethod.objects.filter(owner=request.user,active=True),
            'values':{'bank':bank,'cardholder':cardholder,'network':network,'last4':last4,'expiry':expiry},
        },status=400)
    if PaymentMethod.objects.filter(owner=request.user,active=True).count()>=6:
        messages.error(request,'You can save up to six payment methods.'); return redirect('/payment-methods/')
    PaymentMethod.objects.create(owner=request.user,bank=bank,network=network,last4=last4,
                                 cardholder=cardholder,expiry=expiry)
    messages.success(request,'Payment method saved.'); return redirect('/payment-methods/')

@login_required
@require_POST
@transaction.atomic
def remove(request,pk):
    User.objects.select_for_update().get(pk=request.user.pk)
    card=get_object_or_404(PaymentMethod,pk=pk,owner=request.user)
    Budget.objects.filter(owner=request.user,payment_method=card).update(payment_method=None)
    card.active=False;card.save(update_fields=['active'])
    messages.success(request,'Payment method removed. Categories using it now need a new selection.'); return redirect('/payment-methods/')

@login_required
@require_POST
@transaction.atomic
def select_method(request,pk):
    User.objects.select_for_update().get(pk=request.user.pk)
    budget=get_object_or_404(Budget,pk=pk,owner=request.user)
    value=request.POST.get('method','')
    budget.payment_method=get_object_or_404(PaymentMethod,pk=value,owner=request.user,active=True) if value.isdigit() else None
    budget.save(update_fields=['payment_method'])
    messages.success(request,'Category payment method saved.');return redirect('/')

TOOLS=[{'type':'function','name':'prepare_financial_action','description':'Prepare a budget change or simulated bill payment for user confirmation. Never executes before the user confirms in the chat review message.','parameters':{'type':'object','properties':{'kind':{'type':'string','enum':['adjust_budget','pay_bill']},'category':{'type':'string','enum':['TAQA home bill','Internet & mobile','Gas']},'amount':{'type':['number','null'],'description':'New budget limit; null for payment.'}},'required':['kind','category','amount'],'additionalProperties':False},'strict':True}]

def prepare(user,args):
    kind=args.get('kind');category=args.get('category')
    budget=Budget.objects.filter(owner=user,category=category).first()
    if not budget: raise ValueError('Category not found.')
    if kind=='adjust_budget':
        amount=Decimal(str(args.get('amount')))
        if not amount.is_finite() or not 0<=amount<=1000000: raise ValueError('Invalid budget amount.')
        data={'category':category,'budget_id':budget.pk,'amount':str(amount.quantize(Decimal('.01'))),'previous':str(budget.limit)}
        summary=f'Set {category} budget to AED {data["amount"]}'
    elif kind=='pay_bill':
        bill=Bill.objects.filter(owner=user,category=category,currency='AED',source='samples_aed_v1',paid=False).order_by('period').first()
        if not bill: raise ValueError('There are no outstanding bills in this category.')
        card=budget.payment_method
        if not card or not card.active or card.owner_id!=user.pk: raise ValueError('Select an active payment method for this category first.')
        data={'category':category,'bill_id':bill.pk,'amount':str(bill.amount),'method_id':card.pk,'card':str(card)}
        summary=f'Record payment of AED {bill.amount} to {bill.merchant} using {card}. No money moves.'
    else: raise ValueError('Unsupported action.')
    action=ActionRequest.objects.create(owner=user,kind=kind,arguments=data)
    return {'status':'requires_confirmation','summary':summary,'review_url':f'/actions/{action.pk}/','action_id':action.pk}

@login_required
@transaction.atomic
def confirm(request,pk):
    User.objects.select_for_update().get(pk=request.user.pk)
    action=get_object_or_404(ActionRequest.objects.select_for_update(),pk=pk,owner=request.user)
    data=action.arguments
    if action.status=='pending' and action.created<timezone.now()-timedelta(minutes=15):
        action.status='expired';action.save()
    if request.method=='POST' and action.status=='pending':
        if request.POST.get('decision')=='cancel':
            action.status='cancelled'
        elif request.POST.get('decision')=='confirm':
            if action.kind=='adjust_budget':
                budget=get_object_or_404(Budget,pk=data['budget_id'],owner=request.user)
                if str(budget.limit)!=data['previous']:
                    action.status='expired'
                else:
                    budget.limit=Decimal(data['amount']);budget.save(update_fields=['limit']);action.status='completed'
            else:
                bill=get_object_or_404(Bill.objects.select_for_update(),pk=data['bill_id'],owner=request.user)
                card=PaymentMethod.objects.filter(pk=data['method_id'],owner=request.user,active=True).first()
                if not card or str(bill.amount)!=data['amount']: action.status='expired'
                else:
                    if not bill.paid:
                        Payment.objects.create(bill=bill,payment_method=card,mode='ai_preview');bill.paid=True;bill.save(update_fields=['paid'])
                    action.status='completed'
        action.save(update_fields=['status'])
    if request.headers.get('Accept')=='application/json':
        from .models import Message
        from .views import chat_message
        reviews=Message.objects.filter(owner=request.user,metadata__action_id=action.pk)
        return JsonResponse({'status':action.status,'messages':[chat_message(m) for m in reviews]})
    return render(request,'core/action.html',{'action':action,'data':data})
