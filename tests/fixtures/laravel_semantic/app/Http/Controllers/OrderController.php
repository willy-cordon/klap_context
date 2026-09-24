<?php
namespace App\Http\Controllers;
use App\Services\OrderService;
class OrderController {
    public function __construct(private OrderService $service) {}
    public function store() { return $this->service->create(); }
}
