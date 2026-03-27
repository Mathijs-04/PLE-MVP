<?php

test('rules page loads with game and page query', function () {
    $response = $this->get('/rules?game=aos&page=9');

    $response->assertOk();
});

test('rules page loads with 40k game query', function () {
    $response = $this->get('/rules?game=40k&page=8');

    $response->assertOk();
});
