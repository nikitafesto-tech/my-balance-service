"""
Роутер для платежей YooKassa
"""
import os
import logging
from fastapi import APIRouter, Request, Depends, HTTPException, Body
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from yookassa import Configuration, Payment as YooPayment

from app.database import get_db
from app.dependencies import get_current_user
from app.models import UserWallet, Payment
from app.services.casdoor import update_casdoor_balance

logger = logging.getLogger(__name__)

router = APIRouter(tags=["payments"])

# === YooKassa Configuration ===
if os.getenv("YOOKASSA_SHOP_ID"):
    Configuration.account_id = os.getenv("YOOKASSA_SHOP_ID")
    Configuration.secret_key = os.getenv("YOOKASSA_SECRET_KEY")

# === Constants ===
MIN_AMOUNT = 10
MAX_AMOUNT = 100000


@router.post("/payment/create")
async def create_payment(request: Request, data: dict = Body(...), db: Session = Depends(get_db)):
    """Создание платежа через YooKassa Embedded Widget"""
    user = get_current_user(request, db)
    if not user:
        raise HTTPException(401, "Unauthorized")
    
    # Валидация amount
    amount = data.get("amount")
    if amount is None:
        raise HTTPException(400, "Amount is required")
    
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        raise HTTPException(400, "Amount must be a number")
    
    if amount < MIN_AMOUNT:
        raise HTTPException(400, f"Minimum amount is {MIN_AMOUNT}₽")
    if amount > MAX_AMOUNT:
        raise HTTPException(400, f"Maximum amount is {MAX_AMOUNT}₽")
    
    try:
        payment = YooPayment.create({
            "amount": {"value": str(amount), "currency": "RUB"},
            "confirmation": {"type": "embedded"},
            "capture": True,
            "description": f"Пополнение {user.email}",
            "metadata": {"user_id": user.casdoor_id}
        })
        
        # Сохраняем в БД
        db_payment = Payment(
            yookassa_payment_id=payment.id,
            user_id=user.casdoor_id,
            amount=amount
        )
        db.add(db_payment)
        db.commit()
        
        return {"confirmation_token": payment.confirmation.confirmation_token}
    
    except Exception as e:
        logger.error(f"Payment creation error: {e}", exc_info=True)
        raise HTTPException(500, f"Payment error: {str(e)}")


@router.post("/api/payment/webhook")
async def payment_webhook(request: Request, db: Session = Depends(get_db)):
    """Webhook для обработки уведомлений от YooKassa"""
    try:
        event = await request.json()
        event_type = event.get('event')
        
        logger.info(f"YooKassa webhook received: {event_type}")
        
        if event_type == 'payment.succeeded':
            obj = event.get('object', {})
            payment_id = obj.get('id')
            
            if not payment_id:
                logger.warning("Webhook: missing payment id")
                return {"status": "ok"}
            
            db_payment = db.query(Payment).filter_by(yookassa_payment_id=payment_id).first()
            
            if db_payment and db_payment.status != "succeeded":
                db_payment.status = "succeeded"
                
                wallet = db.query(UserWallet).filter_by(casdoor_id=db_payment.user_id).first()
                if wallet:
                    wallet.balance += db_payment.amount
                    logger.info(f"Balance updated: user={db_payment.user_id}, +{db_payment.amount}₽")
                    
                    # Синхронизация с Casdoor
                    await update_casdoor_balance(db_payment.user_id, wallet.balance)
                
                db.commit()
            else:
                logger.info(f"Payment {payment_id} already processed or not found")
        
        return {"status": "ok"}
    
    except Exception as e:
        logger.error(f"Webhook processing error: {e}", exc_info=True)
        return JSONResponse({"status": "error", "message": str(e)}, status_code=500)
