<?php
namespace App\Http\Controllers;

use App\Services\AuthService;

class AuthController extends Controller
{
    public function __construct(private AuthService $authService) {}

    public function login(): string
    {
        return $this->authService->authenticate();
    }
}
