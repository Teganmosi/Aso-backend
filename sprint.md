# Nigerian Fashion Marketplace MVP — 10-Sprint Roadmap & Verification Guide

> **Project Concept:** *"Chowdeck for Tailors"* — A multi-sided fashion marketplace connecting Nigerian designers with fashion consumers through discovery, commerce, payments, single-vendor fulfillment, SLA management, ledger accounting, and payouts.

## Definition of Done (DoD)
A sprint is strictly defined as **DONE** when:
1. All backend code and automated unit/integration tests for the sprint are implemented and passing cleanly.
2. You (the product owner/tester) have run the step-by-step **Sprint Verification Guide** for that sprint and explicitly confirmed you are satisfied with the working functionality.

---

## Master 10-Sprint Overview

- [x] **Sprint 1: Architecture Foundation, User Identity & Session Auth**
- [x] **Sprint 2: Designer Storefronts & KYC Onboarding**
- [x] **Sprint 3: Category Tree & Product Catalog Engine**
- [x] **Sprint 4: Product Variants & Presigned S3/R2 Media Pipeline**
- [x] **Sprint 5: Single-Vendor Cart Engine**
- [ ] **Sprint 6: Order Engine & Concurrency-Safe Stock Reservation**
- [ ] **Sprint 7: Paystack Payment Gateway & Idempotent Webhook Engine**
- [ ] **Sprint 8: Vendor Order SLA (48h) & Delivery Dispatch Coordination**
- [ ] **Sprint 9: Financial Ledger, Customer Protection Window (72h) & Payout Engine**
- [ ] **Sprint 10: Verified Buyer Reviews, Email Notifications & Launch Polish**

---

## Detailed Sprint Breakdown & Testing Instructions

### ─── Sprint 1: Architecture Foundation, User Identity & Session Auth ───

#### Objectives:
* Scaffold Django modular backend repository structure (`config/`, `apps/`, `requirements/`).
* Configure PostgreSQL database connection and Docker Compose environment.
* Implement `User` model, `CustomerProfile`, and `Address` book in `apps.accounts`.
* Implement **HttpOnly Secure Session / Cookie Authentication** and CSRF token handling.

#### How You Will Test Sprint 1:
1. **Environment Setup Check:**
   * Run local server: `python manage.py runserver` or `docker-compose up`.
   * Open `http://127.0.0.1:8000/admin/` and verify the Django Admin login page loads.
2. **User Registration & Cookie Login:**
   * Send `POST /api/v1/auth/register/` with email, password, name, and phone.
   * Send `POST /api/v1/auth/login/` with credentials.
   * Inspect response headers / cookies: verify `sessionid` cookie is returned with `HttpOnly` and `SameSite` flags.
   * Send `GET /api/v1/me/`: Verify your user details are returned.
3. **Address Book Management:**
   * Send `POST /api/v1/addresses/` to add a shipping address in Lagos.
   * Send `GET /api/v1/addresses/`: Verify the address is returned.

---

### ─── Sprint 2: Designer Storefronts & KYC Onboarding ───

#### Objectives:
* Implement `VendorProfile` (store name, slug, description, logo, city, state) and `BankAccount` in `apps.vendors`.
* Implement vendor onboarding registration API (`POST /api/v1/vendors/register/`).
* Configure Django Admin workflow for staff users (`is_staff=True`) to review and approve designer applications (`PENDING` → `APPROVED`).

#### How You Will Test Sprint 2:
1. **Designer Application Submission:**
   * Send `POST /api/v1/vendors/register/` as a customer to apply for a vendor storefront (*"Lagos Luxe Native"*).
2. **Admin Approval Workflow:**
   * Log into Django Admin at `http://127.0.0.1:8000/admin/vendors/vendorprofile/`.
   * See the new designer application in `PENDING` state. Change status to `APPROVED` and save.
3. **Vendor Profile Verification:**
   * Send `GET /api/v1/me/`: Confirm your user profile now reflects an approved vendor status!
   * Send `GET /api/v1/vendors/lagos-luxe-native/`: Verify public storefront endpoint displays designer details.

---

### ─── Sprint 3: Category Tree & Product Catalog Engine ───

#### Objectives:
* Implement `Category` hierarchy (Men, Women, Traditional, Agbada, Two-Piece, Streetwear).
* Implement `Product` model in `apps.products` (`approval_status` defaults to `PENDING`, base price in Kobo, preparation time days).
* Implement product management APIs for approved vendors.
* Implement public search, category filtering, and sorting selectors (excluding unapproved/draft items).
* Configure Django Admin product moderation pipeline (Approve/Reject products).

#### How You Will Test Sprint 3:
1. **Product Creation (Pending Approval):**
   * As an approved vendor, call `POST /api/v1/products/` with title *"Royal Silk Agbada"*, base price `₦75,000` (`7500000 Kobo`), description, and category ID.
   * Verify product is created with `approval_status = PENDING`.
2. **Public Unapproved Filter Test:**
   * Send `GET /api/v1/products/`: Confirm the product is **NOT** visible to public customers.
3. **Admin Product Approval:**
   * Log into Django Admin, navigate to `Products`, change `approval_status` to `APPROVED` and `status` to `PUBLISHED`.
   * Send `GET /api/v1/products/?search=Agbada`: Confirm product now appears in search!

---

### ─── Sprint 4: Product Variants & Presigned S3/R2 Media Pipeline ───

#### Objectives:
* Implement `ProductVariant` (size, color, SKU, stock quantity, shared base price in Kobo).
* Implement S3/Cloudflare R2 presigned upload URL generator (`POST /api/v1/products/upload-url/`) with MIME whitelist (`image/jpeg`, `image/png`, `image/webp`, `video/mp4`) and vendor ownership boundary.
* Implement `ProductMedia` model and attachment API.
* Implement detailed public product view with full media gallery and variant availability matrix.

#### How You Will Test Sprint 4:
1. **Presigned Media Upload Request:**
   * As approved vendor, call `POST /api/v1/products/upload-url/` with `filename: "agbada.jpg"`, `file_type: "image/jpeg"`.
   * Verify backend returns a presigned S3/R2 upload URL with vendor-scoped object key (`vendors/{vendor_id}/products/{uuid}.jpg`).
2. **Variant Creation & Media Attachment:**
   * Call `POST /api/v1/products/{id}/variants/` to add variants (`XL / Navy / Stock: 5`, `L / Black / Stock: 3`).
   * Attach uploaded media URL to the product.
3. **Public Variant & Gallery Verification:**
   * Send `GET /api/v1/products/{id}/`: Verify full gallery array and variant stock breakdown are returned.

---

### ─── Sprint 5: Single-Vendor Cart Engine ───

#### Objectives:
* Implement `Cart` and `CartItem` models in `apps.cart`.
* Enforce **Single-Vendor Cart Boundary** per customer.
* Implement cart APIs: Add item, remove item, update quantity, view cart subtotal (in Kobo & Naira).

#### How You Will Test Sprint 5:
1. **Add Item to Cart:**
   * Call `POST /api/v1/cart/items/` with a variant ID from **Designer A**.
   * Call `GET /api/v1/cart/`: Verify cart contains the item and calculates subtotal correctly.
2. **Single-Vendor Cart Enforcement Test:**
   * Attempt to add a product variant from **Designer B** to cart.
   * Verify API rejects with HTTP 400 *"Your cart already contains items from Lagos Luxe Native. Checkout or clear cart before adding items from another designer."*
3. **Quantity Updates & Items Removal:**
   * Change quantity to 2: verify subtotal doubles.
   * Delete item: verify cart vendor is reset to null.

---

### ─── Sprint 6: Order Engine & Concurrency-Safe Stock Reservation ───

#### Objectives:
* Implement Order creation service (`POST /api/v1/orders/`) with **pessimistic stock locking** (`select_for_update`).
* Implement 30-minute inventory reservation lifecycle.
* Implement Celery Beat 30-minute payment timeout task (releases reserved stock if unconfirmed).
* Snapshot shipping address and order item prices into `orders_order` and `orders_orderitem`.

#### How You Will Test Sprint 6:
1. **Order Creation & Stock Lock Test:**
   * Note initial stock of `XL Navy Agbada` (5 units).
   * Call `POST /api/v1/orders/` specifying delivery address ID.
   * Verify Order is generated in `PENDING_PAYMENT` status with a unique order number (`ASO-20260809-XXXX`).
   * Check database: Confirm stock of `XL Navy Agbada` was atomically decremented to 4 units!
2. **Address & Price Snapshot Verification:**
   * Edit your saved user address. Fetch the created order: `GET /api/v1/orders/{order_id}/`.
   * Verify the order's snapshotted address remains unchanged!
3. **30-Minute Reservation Release Test:**
   * Run timeout task: `python manage.py run_expired_order_cleanup`.
   * Verify order transitions to `CANCELLED` and variant stock is restored back to 5 units!

---

### ─── Sprint 7: Paystack Payment Gateway & Idempotent Webhook Engine ───

#### Objectives:
* Implement `PaystackProvider` extending `BasePaymentProvider`.
* Implement payment initialization (`POST /api/v1/payments/initialize/`).
* Implement HMAC-SHA512 signature verification & idempotent Webhook handler (`/api/v1/payments/webhook/paystack/`).
* Transition Order from `PENDING_PAYMENT` → `PAID` upon verified payment.

#### How You Will Test Sprint 7:
1. **Payment Initialization:**
   * Call `POST /api/v1/payments/initialize/` for an order.
   * Verify API returns a valid Paystack authorization URL and reference.
2. **Mock Paystack Webhook Execution:**
   * Construct a Paystack `charge.success` JSON payload containing the reference.
   * Compute HMAC-SHA512 signature using `PAYSTACK_SECRET_KEY` and set header `x-paystack-signature`.
   * Send POST request to `/api/v1/payments/webhook/paystack/`. Verify response is `HTTP 200 OK`.
3. **Order State Mutation & Idempotency Test:**
   * Send `GET /api/v1/orders/{order_id}/`: Verify `order_status` is now `PAID`.
   * Send the exact same webhook payload a second time.
   * Verify API returns `HTTP 200 OK`, logs duplicate event in `payments_webhooklog`, and does **not** duplicate operations.

---

### ─── Sprint 8: Vendor Order SLA (48h) & Delivery Dispatch Coordination ───

#### Objectives:
* Implement 48-hour Vendor Acceptance SLA timeout task (auto-refund & stock release).
* Implement Vendor Order Management API (`Accept`, `Preparing`, `Ready for Pickup`).
* Implement `MANUAL_DISPATCH` delivery tracking in `apps.deliveries` syncing with order state machine (`PICKED_UP`, `OUT_FOR_DELIVERY`, `DELIVERED`).

#### How You Will Test Sprint 8:
1. **Vendor Acceptance & Order Lifecycle:**
   * As vendor, view paid orders: `GET /api/v1/vendor/orders/`.
   * Call `POST /api/v1/orders/{id}/accept/` → Status becomes `VENDOR_ACCEPTED`.
   * Call `POST /api/v1/orders/{id}/ready/` → Status becomes `READY_FOR_PICKUP`.
2. **Delivery Status Sync:**
   * Update delivery tracking: mark delivery `IN_TRANSIT`. Verify Order status changes to `OUT_FOR_DELIVERY`.
   * Mark delivery `DELIVERED`. Verify Order status changes to `DELIVERED`.
3. **Vendor SLA Timeout Test:**
   * Create paid order, set `vendor_accept_due_by` to past time. Run SLA task: `python manage.py check_vendor_sla_timeouts`.
   * Verify order is automatically marked `CANCELLED` with note `"Vendor SLA Timeout"` and stock is restored.

---

### ─── Sprint 9: Financial Ledger, Customer Protection Window (72h) & Automated Payout Engine ───

#### Objectives:
* Implement **Automated KYC & Identity Verification** (Paystack NUBAN Name Resolution `GET /bank/resolve` & automated NIN/CAC matching).
* Implement immutable single-entry financial ledger (`payouts_ledgerentry` = Source of Truth).
* Implement materialized `VendorBalance` updating atomically inside the same DB transaction.
* Implement 72-hour Customer Protection Window (auto-completes order `DELIVERED` → `COMPLETED` and releases pending funds to available balance).
* Implement multi-stage Payout state machine (`AVAILABLE` → `PAYOUT_RESERVED` → `PROCESSING` → `SUCCESSFUL` / `FAILED`) with Paystack Transfer API integration.


#### How You Will Test Sprint 9:
1. **Pending Earnings Verification:**
   * Check vendor dashboard `GET /api/v1/payouts/balance/` for a `PAID` order of ₦50,000 (10% commission = ₦5,000).
   * Confirm `pending_balance` shows `₦45,000` (`4500000 Kobo`) and `available_balance` shows `₦0`.
2. **72-Hour Protection Window & Fund Release:**
   * Advance order status to `DELIVERED`. Run completion task: `python manage.py process_completed_orders`.
   * Verify `order_status` becomes `COMPLETED`.
   * Re-check `GET /api/v1/payouts/balance/`: Confirm `pending_balance` is `₦0` and `available_balance` is `₦45,000`!
   * Inspect `payouts_ledgerentry`: Verify explicit ledger entries `EARNING_RELEASE_TO_AVAILABLE` were written.
3. **Payout Withdrawal & Balance Locking Test:**
   * Call `POST /api/v1/payouts/withdraw/` with amount `₦45,000`.
   * Verify `available_balance` drops to `₦0`, `reserved_payout_balance` becomes `₦45,000`, and `PayoutRequest` is created in `PAYOUT_RESERVED` status.
   * Attempt to withdraw another `₦10,000`: Verify API rejects with HTTP 400 *"Insufficient available balance"*.

---

### ─── Sprint 10: Verified Buyer Reviews, Email Notifications & Launch Polish ───

#### Objectives:
* Implement `OrderItem`-linked customer reviews with synchronous rating aggregation on products and vendor profiles.
* Implement Celery transactional HTML emails (Order placed, Payment received, Shipped, Completed).
* Finalize Django Admin dashboards, dispute filters, and bulk status actions.

#### How You Will Test Sprint 10 (End-to-End User Lifecycle):
1. **Verified Buyer Review Test:**
   * As customer on a `COMPLETED` order, call `POST /api/v1/products/{product_id}/reviews/` specifying `order_item_id`, `rating: 5`, `comment: "Exceptional quality tailoring!"`.
   * Send `GET /api/v1/products/{product_id}/`: Verify `average_rating` is updated to `5.00` and `review_count` is `1`.
   * Attempt to submit a second review for the same `order_item_id`: Verify API rejects with HTTP 400 duplicate review error.
2. **Transactional Email Verification:**
   * Check local email backend logs: Verify HTML emails were generated and sent for order placement, payment confirmation, and delivery dispatch.
3. **Final DoD Sign-Off:**
   * Perform complete end-to-end walkthrough test from customer registration to designer payout withdrawal!
