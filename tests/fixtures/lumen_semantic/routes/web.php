<?php
// $router->post('call-vtex', 'ProcessRequestController@callVtex');
$router->group(['middleware' => ['apikey'], 'prefix' => 'api/v1/'], function ($app) {
    $app->post('call-vtex', 'ProcessRequestController@callVtex');
});
