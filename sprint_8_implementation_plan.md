# Implementation Plan — Sprint 8: Vendor Order SLA (48h) & Delivery Dispatch Coordination

Implement the vendor fulfillment lifecycle, 48-hour vendor acceptance SLA guarantee, and manual dispatch/delivery state machine for the Nigerian Fashion Marketplace backend.

---

## User Review Required

> [!IMPORTANT]
> 1. **Order Acceptance SLA**: An order in `PAID` state automatically receives `vendor_accept_due_by = timezone.now() + 48 hours`. If not accepted within this window, `check_vendor_sla_timeouts` cancels the order and restores variant stock.
> 2. **Delivery State Synchronization**: Deliveries are initiated when a vendor marks an order as `READY_FOR_PICKUP`. Status transitions in `Delivery` (`PICKED_UP`, `IN_TRANSIT`, `DELIVERED`) automatically synchronize with `Order.order_status` in real-time.
> 3. **Permissions**: Vendors may only view and mutate orders belonging to their own storefront. Delivery status updates are restricted to the vendor or staff users. Customers can view delivery tracking for their own orders.

---

## Proposed Changes

### Configuration & Settings

#### [MODIFY] [config/settings/base.py](file:///g:/My%20Drive/Aso%20Backend/config/settings/base.py)
- Add `'apps.deliveries'` to `INSTALLED_APPS`.

#### [MODIFY] [config/urls.py](file:///g:/My%20Drive/Aso%20Backend/config/urls.py)
- Include `apps.deliveries.urls` at `api/v1/deliveries/`.

---

### Orders App Enhancements

#### [MODIFY] [apps/orders/models.py](file:///g:/My%20Drive/Aso%20Backend/apps/orders/models.py)
- Add tracking and SLA fields:
  - `vendor_accept_due_by = models.DateTimeField(null=True, blank=True, db_index=True)`
  - `vendor_accepted_at = models.DateTimeField(null=True, blank=True)`
  - `prepared_at = models.DateTimeField(null=True, blank=True)`
  - `ready_for_pickup_at = models.DateTimeField(null=True, blank=True)`

#### [MODIFY] [apps/orders/services.py](file:///g:/My%20Drive/Aso%20Backend/apps/orders/services.py)
- Implement `accept_order(order, user)`: Validates ownership and `PAID` status, transitions to `VENDOR_ACCEPTED`, records `vendor_accepted_at`.
- Implement `move_to_preparing(order, user)`: Validates `VENDOR_ACCEPTED` status, transitions to `PREPARING`, records `prepared_at`.
- Implement `mark_ready_for_pickup(order, user)`: Validates `PREPARING` or `VENDOR_ACCEPTED`, transitions to `READY_FOR_PICKUP`, records `ready_for_pickup_at`, and triggers `Delivery` record creation.
- Implement `process_vendor_sla_timeouts()`: Pessimistically locks and cancels expired `PAID` orders (`vendor_accept_due_by <= now`), restoring variant stock atomically.

#### [MODIFY] [apps/orders/serializers.py](file:///g:/My%20Drive/Aso%20Backend/apps/orders/serializers.py)
- Expose `vendor_accept_due_by`, `vendor_accepted_at`, `prepared_at`, `ready_for_pickup_at` in `OrderSerializer`.
- Add `VendorOrderSerializer` with embedded delivery snapshot.

#### [MODIFY] [apps/orders/views.py](file:///g:/My%20Drive/Aso%20Backend/apps/orders/views.py)
- Add `VendorOrderListView`: `GET /api/v1/vendors/orders/` for authenticated vendors (filter by status).
- Add `VendorOrderDetailView`: `GET /api/v1/vendors/orders/<uuid:order_id>/`.
- Add `OrderAcceptView`: `POST /api/v1/orders/<uuid:order_id>/accept/`.
- Add `OrderPreparingView`: `POST /api/v1/orders/<uuid:order_id>/preparing/`.
- Add `OrderReadyView`: `POST /api/v1/orders/<uuid:order_id>/ready/`.

#### [MODIFY] [apps/orders/urls.py](file:///g:/My%20Drive/Aso%20Backend/apps/orders/urls.py)
- Route `/api/v1/orders/<uuid:order_id>/accept/`, `/preparing/`, `/ready/`, and `/delivery/`.

#### [MODIFY] [apps/vendors/urls.py](file:///g:/My%20Drive/Aso%20Backend/apps/vendors/urls.py)
- Route `/api/v1/vendors/orders/` and `/api/v1/vendors/orders/<uuid:order_id>/`.

#### [NEW] [apps/orders/management/commands/check_vendor_sla_timeouts.py](file:///g:/My%20Drive/Aso%20Backend/apps/orders/management/commands/check_vendor_sla_timeouts.py)
- Management command to execute `process_vendor_sla_timeouts()`.

---

### Payments App Webhook Integration

#### [MODIFY] [apps/payments/services.py](file:///g:/My%20Drive/Aso%20Backend/apps/payments/services.py)
- When `charge.success` updates order to `OrderStatus.PAID`, set `order.vendor_accept_due_by = timezone.now() + timedelta(hours=48)`.

---

### New Deliveries App

#### [NEW] [apps/deliveries/apps.py](file:///g:/My%20Drive/Aso%20Backend/apps/deliveries/apps.py)
- App configuration `DeliveriesConfig`.

#### [NEW] [apps/deliveries/models.py](file:///g:/My%20Drive/Aso%20Backend/apps/deliveries/models.py)
- `DeliveryStatus` TextChoices: `PENDING`, `PICKED_UP`, `IN_TRANSIT`, `DELIVERED`, `FAILED_DELIVERY`.
- `Delivery(UUIDModel)`:
  - `order`: `OneToOneField(Order, on_delete=models.CASCADE, related_name='delivery')`
  - `tracking_number`: `CharField(max_length=100, unique=True, db_index=True)`
  - `carrier_name`: `CharField(max_length=100, default='MANUAL_DISPATCH')`
  - `status`: `CharField(choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING)`
  - `dispatch_notes`: `TextField(null=True, blank=True)`
  - `picked_up_at`: `DateTimeField(null=True, blank=True)`
  - `dispatched_at`: `DateTimeField(null=True, blank=True)`
  - `delivered_at`: `DateTimeField(null=True, blank=True)`

#### [NEW] [apps/deliveries/services.py](file:///g:/My%20Drive/Aso%20Backend/apps/deliveries/services.py)
- `create_delivery_for_order(order, carrier_name, dispatch_notes)`: Generates tracking number and creates `Delivery` record.
- `update_delivery_status(delivery, new_status, notes)`: Updates delivery status and synchronizes `order.order_status` in lockstep (`PICKED_UP` $\rightarrow$ `PICKED_UP`, `IN_TRANSIT` $\rightarrow$ `OUT_FOR_DELIVERY`, `DELIVERED` $\rightarrow$ `DELIVERED`).

#### [NEW] [apps/deliveries/serializers.py](file:///g:/My%20Drive/Aso%20Backend/apps/deliveries/serializers.py)
- `DeliverySerializer`: Read serializer for delivery tracking details.
- `DeliveryStatusUpdateSerializer`: Validation serializer for updating delivery status.

#### [NEW] [apps/deliveries/views.py](file:///g:/My%20Drive/Aso%20Backend/apps/deliveries/views.py)
- `OrderDeliveryDetailView`: `GET /api/v1/orders/<uuid:order_id>/delivery/`
- `DeliveryStatusUpdateView`: `POST /api/v1/deliveries/<uuid:delivery_id>/update-status/`

#### [NEW] [apps/deliveries/urls.py](file:///g:/My%20Drive/Aso%20Backend/apps/deliveries/urls.py)
- Endpoint routing for delivery updates.

---

### Database Migrations

- Run `python manage.py makemigrations orders deliveries` and `python manage.py migrate`.

---

## Verification Plan

### Automated Test Suite

#### [NEW] [tests/test_sprint8_orders_deliveries.py](file:///g:/My%20Drive/Aso%20Backend/tests/test_sprint8_orders_deliveries.py)
1. **Vendor Order Lifecycle Tests:**
   - Vendor can view their orders (`GET /api/v1/vendors/orders/`).
   - Non-vendor or another vendor cannot view or mutate orders.
   - Transition `PAID` $\rightarrow$ `VENDOR_ACCEPTED` (`POST /api/v1/orders/<id>/accept/`).
   - Transition `VENDOR_ACCEPTED` $\rightarrow$ `PREPARING` (`POST /api/v1/orders/<id>/preparing/`).
   - Transition `PREPARING` $\rightarrow$ `READY_FOR_PICKUP` (`POST /api/v1/orders/<id>/ready/`), verifying `Delivery` record is auto-generated.
   - Disallow invalid transitions (e.g. accepting a `PENDING_PAYMENT` or `CANCELLED` order).
2. **Delivery Status Synchronization Tests:**
   - Mark delivery `PICKED_UP` $\rightarrow$ Order status becomes `PICKED_UP`.
   - Mark delivery `IN_TRANSIT` $\rightarrow$ Order status becomes `OUT_FOR_DELIVERY`.
   - Mark delivery `DELIVERED` $\rightarrow$ Order status becomes `DELIVERED` and `delivered_at` is set.
   - Customer and vendor can inspect tracking via `GET /api/v1/orders/<id>/delivery/`.
3. **48-Hour Vendor SLA Timeout Tests:**
   - Create `PAID` order with `vendor_accept_due_by` set in the past.
   - Run `check_vendor_sla_timeouts` command / service.
   - Confirm order status is mutated to `CANCELLED` with cancellation reason `"Vendor SLA Timeout: Order not accepted within 48 hours."`.
   - Confirm reserved product variant stock is restored atomically.
   - Confirm orders with active SLA or already accepted are untouched.

### Test Execution Command
```bash
python manage.py test tests.test_sprint8_orders_deliveries
python manage.py test
```
