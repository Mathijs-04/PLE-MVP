<?php

use Illuminate\Support\Facades\Route;

Route::post('/chat', function () {
    return response()->json(['message' => 'API working']);
});
