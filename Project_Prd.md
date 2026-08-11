# Product Requirements Document (PRD)

## Nigerian Fashion Marketplace — MVP

**Document Version:** 0.1
**Status:** Draft
**Product Stage:** MVP / Pre-Launch
**Backend:** Django + Django REST Framework
**Database:** PostgreSQL
**Primary Market:** Nigeria
**Initial Marketplace Model:** Two-sided fashion marketplace
**Platforms:** Mobile-first Web Application / PWA

---

# 1. Product Overview

## 1.1 Product Concept

The product is a digital marketplace connecting Nigerian fashion designers with customers looking to discover and purchase locally made clothing.

Fashion designers can create vendor storefronts, upload products with images/videos, manage inventory and orders, and receive payouts.

Customers can discover products from multiple Nigerian fashion designers, search and filter products, view designer profiles, place orders, make payments, track orders, and leave reviews.

The marketplace will initially operate as an asset-light platform:

**Designer creates/owns the product → Marketplace provides discovery, commerce, payment and delivery coordination → Customer purchases → Designer fulfills → Customer receives → Designer receives payout.**

---

# 2. Vision

Build the leading marketplace and commerce infrastructure for Nigerian fashion.

The long-term vision is to make the platform the default destination for discovering, purchasing, and experiencing fashion created by independent Nigerian designers.

The eventual platform should enable a customer to think:

> "I want Nigerian fashion."

and immediately think of the marketplace.

---

# 3. Mission

Make it dramatically easier for Nigerian fashion designers to reach customers and dramatically easier for customers to discover and buy high-quality Nigerian-made fashion.

---

# 4. Problem Statement

## 4.1 Vendor Problem

Many emerging Nigerian fashion designers have products but struggle with:

* Customer acquisition
* Product discovery
* Online visibility
* Managing orders
* Receiving payments
* Delivery coordination
* Building trust with new customers
* Managing digital storefronts
* Converting social media attention into sales

Many rely heavily on Instagram, TikTok and WhatsApp.

These platforms are excellent for marketing but are not optimized for end-to-end commerce.

---

## 4.2 Customer Problem

Customers interested in Nigerian fashion often have difficulty:

* Discovering new designers
* Comparing products
* Comparing prices
* Determining quality
* Finding reliable designers
* Knowing available sizes
* Ordering from unfamiliar designers
* Paying securely
* Tracking orders
* Resolving problems

The customer journey is often fragmented across Instagram, WhatsApp, bank transfers and delivery services.

---

# 5. Product Solution

Create a centralized marketplace where:

### Designers

**Upload → List → Sell → Fulfill → Get Paid**

### Customers

**Discover → Compare → Buy → Track → Review**

### Marketplace

**Discovery + Commerce + Trust + Payment + Delivery Coordination**

---

# 6. Target Users

## 6.1 Primary Vendor Persona

### Emerging Nigerian Fashion Designer

Typical characteristics:

* Independent designer/tailor
* Small or growing fashion business
* Primarily operates through Instagram, TikTok or WhatsApp
* Has existing products or collections
* Wants more customers
* May not have a website
* May not have sophisticated e-commerce infrastructure
* Comfortable using smartphones

Initial geographic focus:

**Lagos, Abuja and other major Nigerian cities.**

---

## 6.2 Primary Customer Persona

### Young Nigerian Fashion Consumer

Typical characteristics:

* Smartphone user
* Social-media active
* Interested in fashion
* Comfortable making digital payments
* Wants unique/local fashion
* Values price, quality and convenience
* May already discover fashion through Instagram/TikTok/WhatsApp

Initial demographic focus:

**18–40**

This is a starting hypothesis and should be validated through marketplace data.

---

# 7. MVP Goals

The MVP must prove five things:

### Goal 1 — Supply

Can we successfully onboard independent Nigerian fashion designers?

### Goal 2 — Discovery

Can customers discover products they genuinely want?

### Goal 3 — Conversion

Will customers actually pay for products through the marketplace?

### Goal 4 — Fulfillment

Can vendors successfully fulfill marketplace orders?

### Goal 5 — Trust

Can we create enough trust for customers to purchase from unfamiliar designers?

---

# 8. MVP Success Criteria

The MVP is considered successful when the platform can support this complete lifecycle:

```text
Vendor registers
      ↓
Vendor approved
      ↓
Vendor creates product
      ↓
Product approved
      ↓
Customer discovers product
      ↓
Customer adds product to cart
      ↓
Customer checks out
      ↓
Customer pays
      ↓
Vendor receives order
      ↓
Vendor accepts order
      ↓
Vendor prepares product
      ↓
Delivery pickup
      ↓
Customer receives product
      ↓
Order completed
      ↓
Vendor balance updated
      ↓
Vendor withdraws funds
      ↓
Customer leaves review
```

---

# 9. MVP Scope

## 9.1 Customer Features

### Authentication

Customers can:

* Register
* Login
* Logout
* Reset password
* Manage profile

Authentication may initially support:

* Email
* Phone number

The authentication architecture should allow future OTP-based authentication.

---

## 9.2 Customer Homepage

The homepage should display:

* Featured products
* New products
* Popular products
* Categories
* Featured designers

MVP sections should remain simple.

Potential future sections:

* Trending
* Recommended for you
* Nearby designers
* Personalized collections

---

# 10. Product Discovery

Customers can:

* Browse products
* Search products
* Filter products
* Sort products

### MVP filters

* Category
* Price range
* Size
* Location
* Rating

### MVP sorting

* Newest
* Price low → high
* Price high → low
* Highest rated

---

# 11. Product Details

Each product page should display:

* Product name
* Product images
* Product video
* Price
* Description
* Category
* Available sizes
* Available colors
* Inventory availability
* Vendor name
* Vendor rating
* Vendor location
* Estimated preparation time
* Estimated delivery time
* Reviews

Primary CTA:

**Add to Cart**

Secondary CTA:

**View Designer**

---

# 12. Vendor Storefront

Every approved vendor receives a public storefront.

The storefront displays:

* Vendor name
* Profile image/logo
* Description
* Location
* Verification status
* Rating
* Number of products
* Products
* Reviews

Future:

* Followers
* Collections
* Social links
* Designer story
* Response time
* Completed orders

---

# 13. Shopping Cart

Customers can:

* Add product
* Remove product
* Change quantity
* Select size
* Select variant
* View subtotal
* View estimated delivery
* Proceed to checkout

### MVP constraint

For the initial version, checkout should preferably support **one vendor per order**.

This dramatically simplifies:

* Fulfillment
* Delivery
* Commission calculation
* Vendor payout
* Refunds
* Order management

Multi-vendor carts can be introduced later.

---

# 14. Checkout

Customer provides:

* Full name
* Phone number
* Delivery address
* City
* State
* Delivery instructions

System calculates:

**Product subtotal + delivery fee = total**

Customer selects payment method.

Initial payment provider:

**Paystack or Flutterwave**

Final provider should be selected after technical and commercial evaluation.

---

# 15. Payments

The marketplace must never rely on the frontend to determine payment success.

Payment flow:

```text
Customer creates order
        ↓
Backend creates payment transaction
        ↓
Customer completes payment
        ↓
Payment provider processes payment
        ↓
Provider sends webhook
        ↓
Backend verifies transaction
        ↓
Order marked as PAID
```

Payment webhooks must be:

* Authenticated/verified
* Idempotent
* Logged
* Retry-safe

Frontend redirect alone must never mark an order as paid.

---

# 16. Order Management

Order statuses:

```text
PENDING_PAYMENT
PAID
VENDOR_ACCEPTED
PREPARING
READY_FOR_PICKUP
PICKED_UP
OUT_FOR_DELIVERY
DELIVERED
COMPLETED
CANCELLED
REFUNDED
DISPUTED
```

Not every transition should be available to every user.

Example:

Vendor:

**PAID → ACCEPTED → PREPARING → READY**

Delivery/admin:

**READY → PICKED_UP → OUT_FOR_DELIVERY → DELIVERED**

System:

**DELIVERED → COMPLETED**

---

# 17. Customer Order Tracking

Customers can view:

* Order number
* Product
* Vendor
* Amount
* Payment status
* Order status
* Delivery status
* Delivery address
* Order timeline

Example:

```text
✓ Order placed
✓ Payment confirmed
✓ Designer accepted order
✓ Product being prepared
✓ Ready for pickup
● Out for delivery
○ Delivered
```

---

# 18. Vendor Registration

Vendor onboarding should be intentionally simple.

### Required information

* Full name
* Business/display name
* Phone number
* Email
* Location
* Profile image/logo
* Description

Potential verification information:

* Government-issued ID
* Bank account details
* Business registration information where applicable

KYC requirements should be finalized based on payment-provider and regulatory requirements.

---

# 19. Vendor Dashboard

Vendor dashboard should display:

### Overview

* Total sales
* Orders
* Products
* Available balance
* Pending balance

### Navigation

* Dashboard
* Products
* Orders
* Earnings
* Payouts
* Profile
* Settings

---

# 20. Vendor Product Management

Vendors can:

* Create products
* Edit products
* Delete products
* Publish products
* Unpublish products
* Mark products out of stock

### Product fields

* Name
* Description
* Category
* Price
* Images
* Video
* Sizes
* Colors
* Inventory
* Preparation time
* Location

---

# 21. Product Media

Fashion is a visual marketplace.

Products must support:

### Images

Multiple images per product.

### Video

Short product videos.

The backend should store media in object storage rather than directly on the application server.

Recommended architecture:

```text
Client
  ↓
Backend
  ↓
Object Storage
  ↓
CDN
```

Potential providers:

* Cloudflare R2
* AWS S3

Media should be validated for:

* File type
* File size
* Dimensions
* Security

---

# 22. Vendor Order Management

Vendor sees:

```text
Order #VDO-10023

Product:
Black Senator Set

Size:
XL

Quantity:
1

Amount:
₦55,000

Customer:
John Doe

Delivery:
Lagos

Status:
PAID
```

Vendor actions:

**Accept Order**

→

**Preparing**

→

**Ready for Pickup**

Vendor should not be able to arbitrarily mark an order as delivered.

---

# 23. Vendor Earnings

The system maintains a ledger of vendor earnings.

Example:

```text
Product sale          ₦50,000
Platform commission   -₦5,000
Vendor earnings        ₦45,000
```

Balances should distinguish:

* Pending balance
* Available balance
* Withdrawn balance

---

# 24. Vendor Payouts

Vendor can request withdrawal when funds become available.

Vendor sees:

```text
Available balance

₦145,000

[Withdraw]
```

Withdrawal flow:

```text
Vendor requests payout
        ↓
Backend validates balance
        ↓
Payout created
        ↓
Payment provider processes payout
        ↓
Webhook confirms payout
        ↓
Balance updated
```

All financial changes must be represented in an immutable transaction/ledger system.

The balance should never be treated as the only source of truth.

---

# 25. Reviews and Ratings

Customers can review products after successful delivery.

Review includes:

* Rating: 1–5
* Text
* Optional image

Only customers with a valid completed order should be allowed to review the relevant product.

One customer should not be able to create unlimited reviews for the same order item.

---

# 26. Admin Dashboard

Django Admin can provide the initial internal administrative interface.

Admin capabilities:

### Vendors

* View
* Approve
* Reject
* Suspend
* Verify

### Products

* Approve
* Reject
* Edit
* Hide
* Remove

### Orders

* View
* Update status
* Cancel
* Refund
* Resolve disputes

### Users

* View
* Suspend
* Manage account

### Payments

* View transactions
* View payment status
* Reconcile payments

### Payouts

* View requests
* Approve where necessary
* Monitor failures

### Reviews

* Moderate
* Remove abusive/fraudulent reviews

---

# 27. Marketplace Trust

Trust is a core MVP feature.

The platform should support:

### Verified Vendors

Approved vendors display:

**✓ Verified Designer**

### Reviews

Customer-generated ratings.

### Product media

Real photos/videos.

### Order protection

Customers should have a defined process for:

* Product not received
* Wrong product
* Product materially different from listing
* Vendor cancellation

Exact refund/dispute policies will be defined before launch.

---

# 28. Notifications

MVP notifications:

### Customer

* Order confirmation
* Payment confirmation
* Vendor accepted order
* Order status changes
* Delivery updates
* Order completed

### Vendor

* New order
* Payment confirmed
* Order reminder
* Payout confirmation

Initial channels:

* Email
* In-app notifications

Potential future channel:

* WhatsApp
* SMS
* Push notifications

---

# 29. Search

MVP search should support:

* Product name
* Category
* Vendor name

Example:

> "Agbada"

Future search:

> "Black native outfit under ₦80,000 for a wedding"

This can eventually be powered by semantic/AI search.

---

# 30. Categories

Initial categories should be intentionally limited.

Potential categories:

* Men's Fashion
* Women's Fashion
* Traditional / Native
* Streetwear
* Dresses
* Shirts
* Two-Piece Sets
* Agbada
* Accessories

Categories should be configurable from the backend.

---

# 31. Delivery

The marketplace will initially use third-party delivery providers rather than operating its own fleet.

MVP requirements:

* Delivery fee calculation
* Pickup address
* Customer delivery address
* Delivery status
* Delivery tracking/reference
* Manual admin intervention

The architecture should allow future integration with multiple delivery providers.

---

# 32. Architecture

## Backend

**Django**

**Django REST Framework**

**PostgreSQL**

### Supporting services

* Redis
* Celery
* Object storage
* Payment provider
* Email provider

Redis/Celery should only be introduced where asynchronous/background processing is actually required.

Potential background jobs:

* Email notifications
* Media processing
* Payment reconciliation
* Vendor payout processing
* Order reminders

---

# 33. Backend Architecture

Recommended Django structure:

```text
backend/
│
├── config/
│   ├── settings/
│   ├── urls.py
│   ├── asgi.py
│   └── wsgi.py
│
├── apps/
│   ├── accounts/
│   ├── vendors/
│   ├── products/
│   ├── orders/
│   ├── payments/
│   ├── payouts/
│   ├── reviews/
│   ├── deliveries/
│   ├── notifications/
│   └── marketplace/
│
├── common/
│   ├── permissions/
│   ├── exceptions/
│   ├── storage/
│   ├── pagination/
│   └── utilities/
│
├── manage.py
└── requirements/
```

Django applications should represent meaningful business domains rather than creating an app for every tiny model.

---

# 34. API Architecture

API should be versioned.

Example:

```text
/api/v1/
```

### Accounts

```text
POST   /api/v1/auth/register/
POST   /api/v1/auth/login/
POST   /api/v1/auth/logout/
POST   /api/v1/auth/password-reset/
GET    /api/v1/me/
```

### Vendors

```text
POST   /api/v1/vendors/
GET    /api/v1/vendors/
GET    /api/v1/vendors/{id}/
PATCH  /api/v1/vendors/{id}/
```

### Products

```text
GET    /api/v1/products/
POST   /api/v1/products/
GET    /api/v1/products/{id}/
PATCH  /api/v1/products/{id}/
DELETE /api/v1/products/{id}/
```

### Orders

```text
POST   /api/v1/orders/
GET    /api/v1/orders/
GET    /api/v1/orders/{id}/
POST   /api/v1/orders/{id}/cancel/
POST   /api/v1/orders/{id}/accept/
POST   /api/v1/orders/{id}/ready/
```

### Payments

```text
POST   /api/v1/payments/initialize/
GET    /api/v1/payments/{id}/
POST   /api/v1/payments/webhook/
```

### Reviews

```text
POST   /api/v1/products/{id}/reviews/
GET    /api/v1/products/{id}/reviews/
```

---

# 35. Security Requirements

Security is a first-class requirement.

### Authentication

Use secure token/session mechanisms appropriate for the frontend architecture.

### Authorization

Implement role-based access:

```text
CUSTOMER
VENDOR
ADMIN
```

A vendor must never be able to access another vendor's:

* Orders
* Products
* Customers
* Earnings
* Payouts

### API security

* Rate limiting
* Input validation
* Permission checks
* CSRF protection where applicable
* Secure cookies where applicable
* HTTPS
* Secure headers
* Proper CORS configuration

### Payment security

Never trust:

* Frontend payment status
* Frontend price
* Frontend commission
* Frontend vendor balance

All financial values must be calculated server-side.

---

# 36. Financial Integrity

Money should be stored as integer minor units rather than floating point.

Example:

```text
₦50,000

stored as:

5000000 kobo
```

Never use floating-point numbers for financial calculations.

Every financial event should have a transaction record.

Example:

```text
PAYMENT_RECEIVED
ORDER_FUNDED
COMMISSION_CHARGED
VENDOR_EARNING_CREATED
REFUND_ISSUED
PAYOUT_REQUESTED
PAYOUT_COMPLETED
```

---

# 37. Performance Requirements

Initial target:

* API response: <500ms for common requests under normal load
* Product listing pagination
* Image optimization
* CDN delivery
* Database indexes
* Efficient ORM queries
* Avoid N+1 queries

The architecture should support horizontal scaling later without requiring a rewrite.

---

# 38. Observability

Production system should have:

* Structured logging
* Error tracking
* Request IDs
* Payment event logs
* Order state transition logs
* Audit logs for administrative actions
* Health checks

Critical financial operations must be traceable.

---

# 39. MVP Non-Goals

The following are explicitly excluded from MVP:

* Native iOS application
* Native Android application
* AI stylist
* AI recommendations
* Social feed
* Vendor subscriptions
* Loyalty program
* Live shopping
* Vendor messaging
* Multi-vendor checkout
* International shipping
* International payments
* Marketplace advertising platform
* Advanced analytics
* Automated AI product generation
* Custom tailoring workflow

These can be evaluated after product-market validation.

---

# 40. Initial Business Model

The initial model is transaction-based.

### Proposed hypothesis

Marketplace commission:

**5–15%**

Exact percentage will be validated against:

* Vendor willingness
* Competitor economics
* Payment fees
* Delivery costs
* Refund rates
* Customer acquisition costs
* Vendor margins

The platform should avoid charging vendors upfront during initial marketplace validation.

---

# 41. Initial Launch Strategy

The marketplace will launch with a controlled cohort.

### Phase 1

**10 vendors**

Target:

* 50+ products
* First 10 transactions

### Phase 2

**25 vendors**

Target:

* 150+ products
* 50+ transactions

### Phase 3

**50 vendors**

Target:

* 250–500+ products
* 100+ completed orders

Only after the first cohort demonstrates successful transactions should the marketplace aggressively expand vendor acquisition.

---

# 42. Vendor Acquisition Strategy

Core proposition:

> **List your fashion business for free. Upload your products. We help you find customers. You only pay when you make a sale.**

Initial acquisition channels:

* Instagram
* TikTok
* WhatsApp
* Fashion communities
* Universities
* Fashion schools
* Direct outreach
* Referrals

Potential referral mechanism:

> Existing vendor refers another designer → receives marketplace credit/commission benefit after successful sale.

---

# 43. Customer Acquisition Strategy

Initial channels:

* TikTok
* Instagram
* Influencer partnerships
* Vendor audiences
* Fashion creators
* Referral programs
* Organic search
* Product sharing

A critical strategy:

### Vendors become acquisition channels.

When a designer joins the marketplace, they should be able to share:

> "Shop my collection on [Marketplace]."

This allows the marketplace to leverage the vendor's existing audience.

---

# 44. Core MVP Metrics

## Supply

* Total vendors
* Approved vendors
* Active vendors
* Products/vendor
* Active products

## Demand

* Visitors
* Registered customers
* Product views
* Add-to-cart rate
* Checkout rate
* Conversion rate

## Marketplace

* Orders
* GMV
* Average order value
* Revenue
* Commission
* Orders/vendor

## Retention

* Vendor retention
* Customer repeat purchase rate
* Repeat order frequency

## Operations

* Order fulfillment rate
* Cancellation rate
* Refund rate
* Average delivery time
* Customer support incidents

---

# 45. MVP North Star Metric

The primary early-stage metric is:

## **Completed orders**

Not registrations.

Not downloads.

Not products uploaded.

Not social followers.

The marketplace succeeds when customers successfully purchase products and receive them.

---

# 46. Definition of Done

The MVP is production-ready when:

### Customer

* Can register
* Can browse products
* Can search/filter
* Can view product
* Can view vendor
* Can add to cart
* Can checkout
* Can pay
* Can track order
* Can review completed order

### Vendor

* Can register
* Can be approved
* Can create product
* Can upload media
* Can manage inventory
* Can receive order
* Can update fulfillment status
* Can view earnings
* Can request payout

### Admin

* Can approve vendors
* Can moderate products
* Can manage orders
* Can manage users
* Can monitor payments
* Can manage payouts
* Can manage disputes
* Can moderate reviews

### Platform

* Payment webhooks work reliably
* Financial transactions are auditable
* Permissions are enforced
* Media uploads are secure
* Errors are logged
* Database backups exist
* Production monitoring exists
* Critical workflows have automated tests

---

# 47. Future Roadmap

## Version 1.1

* Multi-vendor carts
* WhatsApp notifications
* Improved search
* Vendor analytics
* Automated delivery integrations
* Product recommendations

## Version 1.2

* AI product descriptions
* Semantic search
* Personalized recommendations
* Vendor CRM
* Promotions
* Coupons

## Version 2

* Native mobile applications
* AI fashion assistant
* Social commerce
* Designer collections
* Vendor advertising
* Advanced analytics

## Long-Term

* Lagos
* Abuja
* Port Harcourt
* Ibadan
* Other Nigerian cities
* West Africa
* African fashion
* Global diaspora market

---

# 48. Product Philosophy

The platform should follow five principles:

### 1. Vendor-first

Make selling effortless.

### 2. Customer-first

Make discovering and buying effortless.

### 3. Trust-first

Never sacrifice marketplace trust for short-term growth.

### 4. Operations-first

A successful transaction matters more than a beautiful feature.

### 5. Data-driven

Build based on observed customer and vendor behavior rather than assumptions.

---

# 49. Ultimate Product Vision

The MVP is not the final product.

The MVP proves the core loop:

```text
Designer
   ↓
Product
   ↓
Marketplace
   ↓
Customer
   ↓
Purchase
   ↓
Delivery
   ↓
Vendor payout
   ↓
Customer review
```

The long-term objective is to turn that loop into a powerful marketplace flywheel:

```text
More designers
      ↓
More products
      ↓
Better discovery
      ↓
More customers
      ↓
More orders
      ↓
More vendor revenue
      ↓
More designers
      ↓
More products
```

The ultimate ambition is to make the platform the **default digital marketplace for discovering and buying Nigerian-made fashion.**
