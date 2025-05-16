## Data Transfer Objects (DTOs)

The following DTOs represent the data structures used to transfer information between the API and clients for the main entities in the GlobeCo Order Service.

---

### BlotterDTO for GET and PUT

Represents a blotter, which is a record grouping financial transactions.

| Field   | Type    | Nullable | Description                                 |
|---------|---------|----------|---------------------------------------------|
| id      | Integer | No       | Unique identifier for the blotter           |
| name    | String  | No       | Name of the blotter                         |
| version | Integer | No       | Optimistic locking version number           |

---
### BlotterDTO for POST

Represents a blotter, which is a record grouping financial transactions.

| Field   | Type    | Nullable | Description                                 |
|---------|---------|----------|---------------------------------------------|
| name    | String  | No       | Name of the blotter                         |
| version | Integer | No       | Optimistic locking version number           |

---

### OrderTypeDTO for GET and PUT

Represents the type of an order.

| Field         | Type    | Nullable | Description                                 |
|---------------|---------|----------|---------------------------------------------|
| id            | Integer | No       | Unique identifier for the order type        |
| abbreviation  | String  | No       | Short code for the order type               |
| description   | String  | No       | Detailed description of the order type      |
| version       | Integer | No       | Optimistic locking version number           |

---

### OrderTypeDTO for POST

Represents the type of an order.

| Field         | Type    | Nullable | Description                                 |
|---------------|---------|----------|---------------------------------------------|
| abbreviation  | String  | No       | Short code for the order type               |
| description   | String  | No       | Detailed description of the order type      |
| version       | Integer | No       | Optimistic locking version number           |

---


### StatusDTO for GET and PUT

Represents the status of an order.

| Field         | Type    | Nullable | Description                                 |
|---------------|---------|----------|---------------------------------------------|
| id            | Integer | No       | Unique identifier for the status            |
| abbreviation  | String  | No       | Short code for the status                   |
| description   | String  | No       | Detailed description of the status          |
| version       | Integer | No       | Optimistic locking version number           |

---

### StatusDTO for POST

Represents the status of an order.

| Field         | Type    | Nullable | Description                                 |
|---------------|---------|----------|---------------------------------------------|
| abbreviation  | String  | No       | Short code for the status                   |
| description   | String  | No       | Detailed description of the status          |
| version       | Integer | No       | Optimistic locking version number           |

---






### OrderDTO for PUT

Represents a trading order in the system.

| Field           | Type             | Nullable | Description                                         |
|-----------------|------------------|----------|-----------------------------------------------------|
| id              | Integer          | No       | Unique identifier for the order                     |
| blotterId       | Integer          | Yes      | Reference to the containing blotter                 |
| statusId        | Integer          | No       | Reference to the order status                       |
| portfolioId     | String (24 char) | No       | ID of the portfolio making the order                |
| orderTypeId     | Integer          | No       | Reference to the order type                         |
| securityId      | String (24 char) | No       | ID of the security being traded                     |
| quantity        | Decimal(18,8)    | No       | Amount of security to trade                         |
| limitPrice      | Decimal(18,8)    | Yes      | Price limit for the order (if applicable)           |
| orderTimestamp  | OffsetDateTime   | No       | When the order was placed                           |
| version         | Integer          | No       | Optimistic locking version number                   |

---



### OrderDTO for POST

Represents a trading order in the system.

| Field           | Type             | Nullable | Description                                         |
|-----------------|------------------|----------|-----------------------------------------------------|
| id              | Integer          | No       | Unique identifier for the order                     |
| blotterId       | Integer          | Yes      | Reference to the containing blotter                 |
| statusId        | Integer          | No       | Reference to the order status                       |
| portfolioId     | String (24 char) | No       | ID of the portfolio making the order                |
| orderTypeId     | Integer          | No       | Reference to the order type                         |
| securityId      | String (24 char) | No       | ID of the security being traded                     |
| quantity        | Decimal(18,8)    | No       | Amount of security to trade                         |
| limitPrice      | Decimal(18,8)    | Yes      | Price limit for the order (if applicable)           |
| orderTimestamp  | OffsetDateTime   | No       | When the order was placed                           |
| version         | Integer          | No       | Optimistic locking version number                   |

---





### OrderWithDetailsDTO for GET

Represents a trading order in the system, including detailed information about its associated blotter, status, and order type.

| Field           | Type                | Nullable | Description                                         |
|-----------------|---------------------|----------|-----------------------------------------------------|
| id              | Integer             | No       | Unique identifier for the order                     |
| blotter         | BlotterDTO          | Yes      | The containing blotter (see [BlotterDTO](#blotterdto)) |
| status          | StatusDTO           | No       | The order status (see [StatusDTO](#statusdto))      |
| portfolioId     | String (24 char)    | No       | ID of the portfolio making the order                |
| orderType       | OrderTypeDTO        | No       | The order type (see [OrderTypeDTO](#ordertypedto))  |
| securityId      | String (24 char)    | No       | ID of the security being traded                     |
| quantity        | Decimal(18,8)       | No       | Amount of security to trade                         |
| limitPrice      | Decimal(18,8)       | Yes      | Price limit for the order (if applicable)           |
| orderTimestamp  | OffsetDateTime      | No       | When the order was placed                           |
| version         | Integer             | No       | Optimistic locking version number                   |


#### Nested DTOs

##### BlotterDTO

| Field   | Type    | Nullable | Description                                 |
|---------|---------|----------|---------------------------------------------|
| id      | Integer | No       | Unique identifier for the blotter           |
| name    | String  | No       | Name of the blotter                         |
| version | Integer | No       | Optimistic locking version number           |

##### StatusDTO

| Field         | Type    | Nullable | Description                                 |
|---------------|---------|----------|---------------------------------------------|
| id            | Integer | No       | Unique identifier for the status            |
| abbreviation  | String  | No       | Short code for the status                   |
| description   | String  | No       | Detailed description of the status          |
| version       | Integer | No       | Optimistic locking version number           |

##### OrderTypeDTO

| Field         | Type    | Nullable | Description                                 |
|---------------|---------|----------|---------------------------------------------|
| id            | Integer | No       | Unique identifier for the order type        |
| abbreviation  | String  | No       | Short code for the order type               |
| description   | String  | No       | Detailed description of the order type      |
| version       | Integer | No       | Optimistic locking version number           |

---


**Notes:**
- All DTOs use types that match the database schema.
- Foreign keys are represented as IDs.
- Nullable fields are indicated in the table.
- The `OrderWithDetailsDTO` provides a richer representation for API responses, embedding related entities directly.
- For lists of orders, you may return a list of `OrderWithDetailsDTO` objects.

