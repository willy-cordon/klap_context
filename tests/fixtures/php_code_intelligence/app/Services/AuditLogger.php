<?php
namespace App\Services;

trait Auditable {}

class AuditLogger
{
    use Auditable;

    public function log(): void {}
}
