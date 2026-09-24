<?php
namespace App\Services;
use App\Jobs\ProcessOrderJob;
class OrderService {
    public function create() { ProcessOrderJob::dispatch(); }
}
