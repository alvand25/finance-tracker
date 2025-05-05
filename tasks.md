# 🧾 Receipt OCR System Implementation Tasks

## ✅ Phase 1: Core Framework – COMPLETE
- [x] Create base handler interface (`handlers/base_handler.py`)
- [x] Implement handler registry for dynamic loading (`handlers/handler_registry.py`)
- [x] Implement store classifier (`store_classifier.py`)
- [x] Implement image preprocessor (`utils/image_preprocessor.py`)
- [x] Create `known_stores.json` for vendor alias matching
- [x] Build core receipt processor (`receipt_processor.py`)

## 🔄 Phase 2: Vendor-Specific Handlers – IN PROGRESS
- [x] Implement generic fallback handler (`handlers/generic_handler.py`)
- [x] Refactor Costco handler into standalone module (`handlers/costco_handler.py`)
- [ ] Refactor Trader Joe's handler
- [ ] Refactor Key Food handler
- [ ] Refactor Walmart handler
- [ ] Identify & extract any other high-priority vendor handlers

## 🧪 Phase 3: Testing Infrastructure – RECOMMENDED BEFORE FULL SERVICE INTEGRATION
- [x] Create CSV test suite (`receipt_test_template.csv`)
- [ ] Enhance test runner (`receipt_test_runner.py`) to:
  - Load CSV scenarios
  - Automatically compare OCR output to expected values
  - Summarize pass/fail results
- [ ] Add per-handler test cases (unit & integration)
- [ ] Add confidence score + error reporting support

## 🔧 Phase 4: Core Processor Refactoring – PENDING
- [ ] Refactor `receipt_service.py` to use modular processor
- [ ] Improve error handling and logging in processor pipeline
- [ ] Add metadata enrichment (e.g. OCR version, language, processing time)
- [ ] Add confidence scoring & validation checks to output

## 🔁 Phase 5: CLI & Automation – PENDING
- [ ] Update CLI to interface with `receipt_processor.py`
- [ ] Add debug flags (e.g. `--force-handler`, `--dry-run`, `--verbose`)
- [ ] Add batch processing support (`--dir ./samples`)
- [ ] Update README and dev onboarding instructions

## 🎨 Phase 6: UX + Expense System Polish – NEW PRIORITY
- [x] **Task 1: Improve Receipt Upload UX:**
  - [x] Replace current button with drag & drop zone + "Click to upload"
  - [x] Show receipt preview on upload
  - [x] Add loader during OCR request with processing indicator
  - [x] Display processing success/failure with visual feedback
  - [x] Add validation error display

- [x] **Task 2: Shared/Personal Item Management:**
  - [x] Add distinct "Shared Items" and "Personal Items" sections
  - [x] Implement checkbox-controlled item assignment
  - [x] Add inline editing for item name and price
  - [x] Implement suspicious item flagging (yellow background + "!" icon)
  - [x] Add "Show Suspicious Items" toggle with auto-hide default

- [x] **Task 3: Live Calculation Logic:**
  - [x] Implement real-time balance updates on item selection
  - [x] Add dynamic "Who owes who" calculation  
  - [x] Update dashboard totals without page reload
  - [x] Save updated data to monthly JSON storage

- [x] **Task 4: Export System:**
  - [x] Create `utils/export.py` module
  - [x] Add "Download CSV" button to dashboard and month views
  - [x] Implement export that includes all itemized shared expenses
  - [x] Add summary table of payment balances to export
  - [x] Create Flask route for handling export requests

- [x] **Task 5: Mobile API Prep:**
  - [x] Create POST endpoint: `/api/upload-receipt`
  - [x] Implement multipart/form-data image upload handling
  - [x] Return JSON response with parsed items and metadata
  - [ ] Add API authentication mechanism
  - [ ] Create API documentation

## 🌟 Concurrent OCR Improvements (Background Tasks)
- [ ] **Regex Pattern Enhancements:**
  - [ ] Improve total regex to accept whitespace/misaligned format
  - [ ] Add logic to use subtotal as total if equal
  - [ ] Implement fallback for known stores (e.g., Costco)
  - [ ] Add validation notes for fallback logic

- [x] **Validation Improvements:**
  - [x] Add check for item_sum vs total mismatch (>10% difference)
  - [x] Flag receipts with validation issues
  - [x] Add visual indicators for flagged receipts

- [x] **Store Name Parsing:**
  - [x] Add fuzzy correction for similar store names
  - [ ] Implement known brand matching (>80% similarity)
  - [ ] Create store name alias database

## Current Implementation Status
- Core framework components (Phase 1) are complete and verified working
- Phase 2 in progress: Generic handler and Costco handler complete, other vendor handlers being extracted
- Phase 3 testing infrastructure recommended before proceeding with service integration
- Phases 4-5 pending completion of vendor handlers and testing framework
- **Phase 6 is now completed** - All UX improvements have been successfully implemented, while OCR fixes continue in background 