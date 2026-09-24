<?php
namespace App\Http\Controllers;

use App\Services\ProcessRequestService;

class ProcessRequestController
{
    private $processRequestService;

    public function __construct(ProcessRequestService $processRequestService)
    {
        $this->processRequestService = $processRequestService;
    }

    public function callVtex($request)
    {
        return $this->processRequestService->validateRequest($request);
    }
}
