<?php
namespace App\Jobs;
class ProcessOrderJob implements ShouldQueue {
    public function handle() { Http::post('https://orders.example.test'); }
}
