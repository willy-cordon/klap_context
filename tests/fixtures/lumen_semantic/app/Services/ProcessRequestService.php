<?php
namespace App\Services;

class ProcessRequestService
{
    private $vtexService;

    public function __construct(VtexService $vtexService)
    {
        $this->vtexService = $vtexService;
    }

    public function validateRequest($request)
    {
        return $this->callVtex($request);
    }

    public function callVtex($request)
    {
        return $this->vtexService->searchOrderVtex($request);
    }
}
