<?php
namespace App\Services;

class VtexService
{
    public function searchOrderVtex($request)
    {
        return $this->getOrderDetails($request);
    }

    public function getOrderDetails($request)
    {
        return [];
    }
}
