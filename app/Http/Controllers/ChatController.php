<?php

namespace App\Http\Controllers;

use App\Services\AiService;
use Illuminate\Http\Request;

class ChatController extends Controller
{
    public function ask(Request $request, AiService $aiService)
    {
        $validated = $request->validate([
            'question' => 'required_without:message|string',
            'message' => 'required_without:question|string',
            'game' => 'required|string|in:aos,40k,wh40k',
        ]);

        $question = $validated['question'] ?? $validated['message'];

        return response()->json($aiService->ask($question, $validated['game']));
    }
}
