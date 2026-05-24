<?php

use Illuminate\Support\Facades\Http;

beforeEach(function () {
    config(['services.ai.url' => 'http://fake-ai.test']);
});

function fakeAiSuccessResponse(): array
{
    return [
        'short_answer' => 'Yes.',
        'detailed_answer' => 'You may reinforce the unit.',
        'source' => 'WH Age of Sigmar Core Rules (4th ed.)',
        'certainty' => 1,
    ];
}

test('accepts question and game and returns ai response', function () {
    Http::fake([
        'fake-ai.test/ask' => Http::response(fakeAiSuccessResponse(), 200),
    ]);

    $response = $this->postJson('/api/chat', [
        'question' => 'Can I reinforce this unit?',
        'game' => 'aos',
    ]);

    $response->assertSuccessful()
        ->assertJson([
            'short_answer' => 'Yes.',
            'detailed_answer' => 'You may reinforce the unit.',
            'source' => 'WH Age of Sigmar Core Rules (4th ed.)',
            'certainty' => 1,
        ]);
});

test('accepts message as alias for question', function () {
    Http::fake([
        'fake-ai.test/ask' => Http::response(fakeAiSuccessResponse(), 200),
    ]);

    $response = $this->postJson('/api/chat', [
        'message' => 'Can I reinforce this unit?',
        'game' => 'aos',
    ]);

    $response->assertSuccessful()
        ->assertJsonPath('short_answer', 'Yes.');
});

test('normalizes 40k to wh40k in outbound request', function () {
    Http::fake([
        'fake-ai.test/ask' => Http::response(fakeAiSuccessResponse(), 200),
    ]);

    $this->postJson('/api/chat', [
        'question' => 'What is Devastating Wounds?',
        'game' => '40k',
    ])->assertSuccessful();

    Http::assertSent(function ($request) {
        return $request->url() === 'http://fake-ai.test/ask'
            && $request['game'] === 'wh40k'
            && $request['question'] === 'What is Devastating Wounds?';
    });
});

test('rejects missing question and message', function () {
    $response = $this->postJson('/api/chat', [
        'game' => 'aos',
    ]);

    $response->assertUnprocessable()
        ->assertJsonValidationErrors(['question', 'message']);
});

test('rejects invalid game', function () {
    $response = $this->postJson('/api/chat', [
        'question' => 'Can I reinforce this unit?',
        'game' => 'invalid',
    ]);

    $response->assertUnprocessable()
        ->assertJsonValidationErrors(['game']);
});

test('forwards ai service failure', function () {
    Http::fake([
        'fake-ai.test/ask' => Http::response('Service unavailable', 503),
    ]);

    $response = $this->postJson('/api/chat', [
        'question' => 'Can I reinforce this unit?',
        'game' => 'aos',
    ]);

    $response->assertSuccessful()
        ->assertJson([
            'error' => 'AI service request failed',
            'status' => 503,
            'body' => 'Service unavailable',
        ]);
});

test('accepts valid game values', function (string $game) {
    Http::fake([
        'fake-ai.test/ask' => Http::response(fakeAiSuccessResponse(), 200),
    ]);

    $this->postJson('/api/chat', [
        'question' => 'Can I reinforce this unit?',
        'game' => $game,
    ])->assertSuccessful();
})->with([
    'aos' => ['aos'],
    '40k' => ['40k'],
    'wh40k' => ['wh40k'],
]);
