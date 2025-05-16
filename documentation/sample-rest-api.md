## REST API Documentation

The following REST APIs are recommended for managing blotters, order types, statuses, and orders in the GlobeCo Order Service. All endpoints return JSON and use standard HTTP status codes.

---

### Blotter Endpoints

| Method | Path              | Request Body         | Response Body        | Description                       |
|--------|-------------------|---------------------|----------------------|-----------------------------------|
| GET    | /api/v1/blotters     |                     | [BlotterDTO]         | List all blotters                 |
| GET    | /api/v1/blotter/{id}|                     | BlotterDTO           | Get a blotter by ID               |
| POST   | /api/v1/blotters     | BlotterDTO (POST)   | BlotterDTO           | Create a new blotter              |
| PUT    | /api/v1/blotter/{id}| BlotterDTO (PUT)    | BlotterDTO           | Update an existing blotter        |
| DELETE | /api/v1/blotter/{id}?version={version}|                     |                      | Delete a blotter by ID            |

---

### Order Type Endpoints

| Method | Path                   | Request Body           | Response Body        | Description                       |
|--------|------------------------|-----------------------|----------------------|-----------------------------------|
| GET    | /api/v1/orderTypes       |                       | [OrderTypeDTO]       | List all order types              |
| GET    | /api/v1/orderTypes/{id}  |                       | OrderTypeDTO         | Get an order type by ID           |
| POST   | /api/v1/orderTypes       | OrderTypeDTO (POST)   | OrderTypeDTO         | Create a new order type           |
| PUT    | /api/v1/orderType/{id}  | OrderTypeDTO (PUT)    | OrderTypeDTO         | Update an existing order type     |
| DELETE | /api/v1/orderType/{id}?version={version}  |                       |                      | Delete an order type by ID        |

---

### Status Endpoints

| Method | Path              | Request Body         | Response Body        | Description                       |
|--------|-------------------|---------------------|----------------------|-----------------------------------|
| GET    | /api/v1/statuses     |                     | [StatusDTO]          | List all statuses                 |
| GET    | /api/v1/status/{id}|                     | StatusDTO            | Get a status by ID                |
| POST   | /api/v1/statuses     | StatusDTO (POST)    | StatusDTO            | Create a new status               |
| PUT    | /api/v1/status/{id}| StatusDTO (PUT)     | StatusDTO            | Update an existing status         |
| DELETE | /api/v1/status/{id}?version={version}|                     |                      | Delete a status by ID             |

---

### Order Endpoints

| Method | Path              | Request Body         | Response Body            | Description                                 |
|--------|-------------------|---------------------|--------------------------|---------------------------------------------|
| GET    | /api/v1/orders       |                     | [OrderWithDetailsDTO]    | List all orders (with details)              |
| GET    | /api/v1/order/{id}  |                     | OrderWithDetailsDTO      | Get an order by ID (with details)           |
| POST   | /api/v1/orders       | OrderDTO (POST)     | OrderWithDetailsDTO      | Create a new order                          |
| PUT    | /api/v1/order/{id}  | OrderDTO (PUT)      | OrderWithDetailsDTO      | Update an existing order                    |
| DELETE | /api/v1/order/{id}?version={version}  |                     |                        | Delete an order by ID                       |

---

#### Notes
- All POST and PUT endpoints expect the corresponding DTO in the request body.
- All GET endpoints return the DTO or a list of DTOs as described above.
- The `OrderWithDetailsDTO` includes nested `BlotterDTO`, `StatusDTO`, and `OrderTypeDTO` objects for richer responses.
- Standard error responses (e.g., 404 Not Found, 400 Bad Request, 409 Conflict) should be used as appropriate.

---

**Example: Create Order Request (POST /api/v1/orders)**
```json
{
  "blotterId": 1,
  "statusId": 2,
  "portfolioId": "5f47ac10b8e4e53b8cfa9b1a",
  "orderTypeId": 3,
  "securityId": "5f47ac10b8e4e53b8cfa9b1b",
  "quantity": 100.00000000,
  "limitPrice": 50.25000000,
  "orderTimestamp": "2024-06-01T12:00:00Z",
  "version": 1
}
```

**Example: Get Order Response (GET /api/v1/orders/42)**
```json
{
  "id": 42,
  "blotter": {
    "id": 1,
    "name": "Equities",
    "version": 1
  },
  "status": {
    "id": 2,
    "abbreviation": "NEW",
    "description": "New Order",
    "version": 1
  },
  "portfolioId": "5f47ac10b8e4e53b8cfa9b1a",
  "orderType": {
    "id": 3,
    "abbreviation": "LMT",
    "description": "Limit Order",
    "version": 1
  },
  "securityId": "5f47ac10b8e4e53b8cfa9b1b",
  "quantity": 100.00000000,
  "limitPrice": 50.25000000,
  "orderTimestamp": "2024-06-01T12:00:00Z",
  "version": 1
}
```
