<?php
namespace App\Services;

class JwtService
{
    public static function createToken(): string
    {
        return 'token';
    }

    public function validate(): bool
    {
        return true;
    }
}
