# Warhammer Rule Assistant

## Project Summary
Warhammer Rule Assistant is a question-answering tool for tabletop Warhammer rules. It answers rule-related questions using official rule sources.

## Core Functionality
- **Rules Chat:** Users ask rules questions and receive a short answer, detailed explanation, source summary, and certainty rating.
- **Game Selection:** The chat supports Warhammer Age of Sigmar and Warhammer 40,000.
- **Rules Retrieval:** The Python service searches indexed rules text before asking the AI model to answer from that context.
- **Faction Support:** Faction rule data can be used for unit, ability, points, and army-list style questions.
- **Rules Library:** The `/rules` page provides access to core rule PDFs through the app.

## Tech Summary
- **Backend:** Laravel API endpoint (`/api/chat`) receives user questions.
- **AI Service:** Python FastAPI endpoint (`/ask`) processes questions using AI and returns answers.
- **Frontend:** Laravel + Vite + Vue provides the chat interface.
- **Flow:** User asks a question in the UI -> Laravel forwards it to Python -> Python uses AI and returns an answer -> Laravel sends it back to the UI.

## Data Summary
- **Core Rules:** Official Warhammer PDF rule documents are used as primary rule references.
- **Faction Rules:** The GitHub BSData repository is used for faction-specific rule data.
