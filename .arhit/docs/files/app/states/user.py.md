# app/states/user.py

FSM-стейты пользовательского флоу. BuyFlow: choosing_plan (выбор тарифа), entering_promo (ввод промокода), confirming (просмотр итоговой цены/применённого промо). PromoActivate: waiting_code (ввод кода для активации free_days без оплаты). Стейт-данные (plan_id, promo_id) хранятся через FSMContext.update_data; стейт очищается после отправки invoice, потому что pre_checkout/successful_payment приходят без стейта и используют payload invoice'а для переноса plan_id/promo_id.
