const express = require('express');
const app = express();
class OrderService { create() { return true; } }
const service = new OrderService();
function createOrder(req, res) { return service.create(); }
app.post('/orders', createOrder);
