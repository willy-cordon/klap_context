<?php
namespace Tests\Feature;

use App\Services\AuthService;

class AuthTest
{
    public function test_authentication(): void
    {
        new AuthService();
    }
}
