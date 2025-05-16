## Entity Relationship Diagram

<img src="./images/order-service.png">



```
+-------------+       +----------------+       +-------------+
|   blotter   |       |     order      |       | order_type  |
+-------------+       +----------------+       +-------------+
| PK id       |<----->| PK id          |<----->| PK id       |
|    name     |       |    blotter_id  |       |    abbrev.  |
|    version  |       |    status_id   |       |    desc.    |
+-------------+       |    portfolio_id|       |    version  |
                      |    order_type_id|      +-------------+
                      |    security_id |
                      |    quantity    |       +-------------+
                      |    limit_price |       |   status    |
                      |    order_time  |<----->| PK id       |
                      |    version     |       |    abbrev.  |
                      +----------------+       |    desc.    |
                                               |    version  |
                                               +-------------+
```

## Tables

### blotter

A blotter is a record of financial transactions, typically used to organize and group orders.

| Column  | Data Type   | Constraints    | Description                       |
|---------|-------------|----------------|-----------------------------------|
| id      | serial      | PK, NOT NULL   | Unique identifier                 |
| name    | varchar(60) | NOT NULL       | Name of the blotter               |
| version | integer     | NOT NULL, DEF 1 | Optimistic locking version number |

#### Initialization Data for `blotter`

| name | version |
| --- | --- |
| Default | 1 |
| Equity | 1 |
| Fixed Income | 1 |
| Hold | 1 |
| Crypto | 1 |
---



### order

The main entity representing a trading order in the system.

| Column          | Data Type     | Constraints        | Description                            |
|-----------------|---------------|-------------------|----------------------------------------|
| id              | serial        | PK, NOT NULL      | Unique identifier                      |
| blotter_id      | integer       | FK to blotter.id  | Reference to the containing blotter    |
| status_id       | integer       | FK, NOT NULL      | Reference to order status              |
| portfolio_id    | char(24)      | NOT NULL          | ID of the portfolio making the order   |
| order_type_id   | integer       | FK, NOT NULL      | Reference to order type                |
| security_id     | char(24)      | NOT NULL          | ID of the security being traded        |
| quantity        | decimal(18,8) | NOT NULL          | Amount of security to trade            |
| limit_price     | decimal(18,8) |                   | Price limit for the order (if applicable) |
| order_timestamp | timestamptz   | NOT NULL, DEF NOW | When the order was placed              |
| version         | integer       | NOT NULL, DEF 1   | Optimistic locking version number      |

### order_type

Defines the various types of orders available in the system.

| Column       | Data Type   | Constraints    | Description                       |
|-------------|-------------|----------------|-----------------------------------|
| id          | serial      | PK, NOT NULL   | Unique identifier                 |
| abbreviation | varchar(10) | NOT NULL       | Short code for the order type     |
| description | varchar(60) | NOT NULL       | Detailed description of order type |
| version     | integer     | NOT NULL, DEF 1 | Optimistic locking version number |

#### Initialization data for `order_type`

| abbreviation | description | version |
| --- | --- | --- |
| BUY | Buy | 1 |
| SELL | Sell | 1 |
| SHORT | Sell to Open | 1 |
| COVER | Buy to Close | 1 |
| EXRC | Exercise | 1 |
---


### status

Defines the possible statuses an order can have.

| Column       | Data Type   | Constraints    | Description                       |
|-------------|-------------|----------------|-----------------------------------|
| id          | serial      | PK, NOT NULL   | Unique identifier                 |
| abbreviation | varchar(20) | NOT NULL       | Short code for the status         |
| description | varchar(60) | NOT NULL       | Detailed description of status    |
| version     | integer     | NOT NULL, DEF 1 | Optimistic locking version number |

#### Initialization Data for `status`

| abbreviation | description | version |
| --- | --- | --- |
| NEW | New | 1 |
| SENT | Sent | 1 |
| WORK | In progress | 1 |
| FULL | Filled | 1 |
| PART | Partial fill | 1 |
| HOLD | Hold | 1 |
| CNCL | Cancel | 1 |
| CNCLD | Cancelled | 1 |
| CPART | Cancelled with partial fill | 1 |
| DEL | Delete | 1 |
---

## Relationships

1. **blotter to order (1:N)**
   - A blotter can contain multiple orders
   - An order can optionally belong to one blotter
   - If a blotter is deleted, the blotter_id in associated orders is set to NULL

2. **order_type to order (1:N)**
   - An order type can be used by multiple orders
   - Each order must have exactly one order type
   - Order types cannot be deleted if they're referenced by orders

3. **status to order (1:N)**
   - A status can apply to multiple orders
   - Each order must have exactly one status
   - Status records cannot be deleted if they're referenced by orders

## Design Notes

1. The database uses PostgreSQL version 17.0
2. All tables include a version column for optimistic locking
3. The model uses 24-character strings for external IDs (portfolio_id, security_id), likely to accommodate MongoDB ObjectIDs
4. Decimal columns use high precision (18,8) to accommodate financial calculations
5. Orders have ON DELETE RESTRICT for status and order_type relationships, preventing deletion of referenced records
6. All timestamp fields use timestamptz (timestamp with time zone) to ensure proper timezone handling
