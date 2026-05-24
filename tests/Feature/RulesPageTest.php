<?php

use Inertia\Testing\AssertableInertia as Assert;

test('rules page loads with game and page query', function () {
    $response = $this->get('/rules?game=aos&page=9');

    $response->assertOk()
        ->assertInertia(fn (Assert $page) => $page
            ->component('Rules'),
        );
});

test('rules page loads with 40k game query', function () {
    $response = $this->get('/rules?game=40k&page=8');

    $response->assertOk()
        ->assertInertia(fn (Assert $page) => $page
            ->component('Rules'),
        );
});
