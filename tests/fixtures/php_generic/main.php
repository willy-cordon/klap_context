<?php
function main() {
    $worker = new Worker();
    $worker->run();
}

class Worker {
    public function run() { return true; }
}
