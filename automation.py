import sys
import asyncio
import json
import re
from playwright.async_api import async_playwright

async def process_freefire_topup(player_uid: str, diamond_amount: str, voucher_code: str, pin_code: str = ""):
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--window-size=1280,800",
            ]
        )

        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={'width': 1280, 'height': 800},
            locale="en-US"
        )
        
        page = await context.new_page()

        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)

        try:
            # ১. গ্যারেনা পেজ লোড ও লগইন
            await page.goto("https://shop.garena.my/?app=100067&channel=202953", wait_until="domcontentloaded")
            await page.wait_for_timeout(2000)

            try:
                close_btn = page.locator("button.close, .modal-close, div[role='button']:has-text('Close'), div[role='button']:has-text('OK')").first
                if await close_btn.is_visible(timeout=2000):
                    await close_btn.click()
            except Exception:
                pass

            uid_input = page.locator("input[placeholder*='player ID' i], input[placeholder*='Player ID' i], input[type='text']").first
            await uid_input.wait_for(timeout=15000)
            await uid_input.click()
            await uid_input.fill(str(player_uid).strip())
            await page.wait_for_timeout(500)

            login_btn = page.locator("button:has-text('Login'), div[role='button']:has-text('Login'), .login-btn").first
            if await login_btn.is_visible(timeout=2000):
                await login_btn.click()
            else:
                await uid_input.press("Enter")

            await page.wait_for_timeout(2000)

            # ২. Proceed to Payment ক্লিক
            proceed_btn = page.locator("button:has-text('Proceed to Payment'), div[role='button']:has-text('Proceed to Payment')").first
            await proceed_btn.wait_for(state="visible", timeout=15000)
            await proceed_btn.click()

            await page.wait_for_timeout(4000)

            # ৩. ডায়মন্ড সিলেক্ট করা
            num_only = re.sub(r"\D", "", str(diamond_amount))
            await page.evaluate("""
                (targetNum) => {
                    const elements = Array.from(document.querySelectorAll('button, a, div[role="button"], div'));
                    const match = elements.reverse().find(el => {
                        if (!el.innerText) return false;
                        const words = el.innerText.trim().split(/\\s+/);
                        return words.includes(targetNum) && words.some(w => w.toLowerCase().includes('diamond'));
                    });
                    if (match) {
                        const clickable = match.closest('button, a, [role="button"]') || match;
                        clickable.scrollIntoView();
                        clickable.click();
                    }
                }
            """, num_only)

            await page.wait_for_timeout(3000)

            # ভাউচার পার্সিং
            if " " in voucher_code or "," in voucher_code:
                parts = re.split(r'[\s,]+', voucher_code.strip())
                raw_serial = parts[0]
                raw_pin = parts[1] if len(parts) > 1 else pin_code
            else:
                raw_serial = voucher_code
                raw_pin = pin_code

            clean_serial = re.sub(r'[^A-Za-z0-9]', '', raw_serial).strip().upper()
            clean_pin = re.sub(r'[^A-Za-z0-9]', '', raw_pin).strip()

            # ৪. Physical Vouchers ট্যাব হ্যান্ডলিং
            physical_tab = page.locator("text=Physical Vouchers").first
            if await physical_tab.is_visible():
                if not await page.locator("text='UniPin Voucher'").is_visible():
                    await physical_tab.click()
                    await page.wait_for_timeout(1000)

            # ৫. UniPin Voucher / UP Gift Card সিলেক্ট করা
            target_card_text = "UniPin Voucher" if clean_serial.startswith("BDMB") else "UP Gift Card"
            
            card_locator = page.locator(f"text='{target_card_text}'").first
            await card_locator.wait_for(state="visible", timeout=15000)
            
            await page.evaluate("""
                (cardText) => {
                    const el = Array.from(document.querySelectorAll('*')).find(e => e.innerText && e.innerText.trim() === cardText);
                    if (el) {
                        const box = el.closest('div[class*="channel"], div[class*="item"], div[role="button"]') || el.parentElement || el;
                        box.click();
                    }
                }
            """, target_card_text)
            
            await page.wait_for_timeout(2000)

            sub_continue = page.locator("button:has-text('Continue'), button:has-text('Proceed'), div[role='button']:has-text('Continue')").first
            if await sub_continue.is_visible(timeout=2000):
                await sub_continue.click()

            await page.wait_for_timeout(3000)

            # ৬. সিরিয়াল ও পিন ইনপুট স্কোপ লোকেট করা
            target_scope = page
            for _ in range(10):
                for frame in [page] + page.frames:
                    inp = frame.locator("input[placeholder*='Serial' i], input[placeholder*='UPBD' i], input[name*='serial' i], input[id*='serial' i], input[type='text']")
                    if await inp.count() > 0 and await inp.first.is_visible():
                        target_scope = frame
                        break
                if target_scope != page:
                    break
                await page.wait_for_timeout(1000)

            # ৭. সিরিয়াল ফিল্ড
            serial_input = target_scope.locator("input[placeholder*='UPBD' i], input[placeholder*='Serial' i], input[name*='serial' i], input[type='text']").first
            await serial_input.wait_for(state="visible", timeout=15000)
            await serial_input.click()
            await serial_input.fill(clean_serial)
            await page.wait_for_timeout(500)

            # ৮. পিন ফিল্ড
            pin_inputs = target_scope.locator("input[type='password'], input[name*='pin' i], input[id*='pin' i]")
            pin_count = await pin_inputs.count()

            if pin_count >= 4 and len(clean_pin) >= 12:
                chunks = [clean_pin[i:i+4] for i in range(0, len(clean_pin), 4)]
                for idx, chunk in enumerate(chunks[:4]):
                    inp = pin_inputs.nth(idx)
                    await inp.click()
                    await inp.fill(chunk)
                    await page.wait_for_timeout(100)
            elif pin_count > 0:
                await pin_inputs.first.click()
                if len(clean_pin) == 16:
                    formatted_pin = "-".join([clean_pin[i:i+4] for i in range(0, 16, 4)])
                    await pin_inputs.first.fill(formatted_pin)
                else:
                    await pin_inputs.first.fill(clean_pin)

            await page.wait_for_timeout(1500)

            # ৯. কনফার্ম ক্লিক
            confirm_btn = target_scope.locator("input[type='submit'][value='Confirm'], input[value='Confirm'], button:has-text('Confirm')").first
            if await confirm_btn.is_visible(timeout=3000):
                await confirm_btn.scroll_into_view_if_needed()
                await confirm_btn.click(force=True)
            else:
                await target_scope.evaluate("""
                    const btn = document.querySelector("input[type='submit'][value='Confirm']") || 
                                document.querySelector("input[value='Confirm']");
                    if (btn) btn.click();
                """)

            await page.wait_for_timeout(7000)

            # ১০. ফলাফল ভেরিফিকেশন
            content = await target_scope.content()
            main_content = (await page.content()).lower()
            current_url = page.url.lower()

            if "consumed voucher" in main_content or "consumed%20voucher" in current_url:
                return json.dumps({"success": False, "reason": "CONSUMED_VOUCHER", "message": "Voucher is already consumed/used."})

            success_keywords = [
                "transaction successful",
                "transactions successful",
                "successful",
                "transaction success",
                "transactions success",
                "success",
                "completed",
            ]

            if any(word in main_content or word in content.lower() for word in success_keywords):
                return json.dumps({"success": True, "message": "Topup Completed Successfully!"})
            else:
                return json.dumps({"success": False, "reason": "FAILED", "message": "Transaction Failed or Invalid Voucher Error."})

        except Exception as e:
            try:
                await page.screenshot(path="debug_error.png", full_page=True)
            except Exception:
                pass
            return json.dumps({"success": False, "reason": "ERROR", "message": str(e)})

        finally:
            await browser.close()

if __name__ == "__main__":
    if len(sys.argv) > 4:
        p_uid, d_amount, v_serial, v_pin = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
        res = asyncio.run(process_freefire_topup(p_uid, d_amount, v_serial, v_pin))
    elif len(sys.argv) == 4:
        p_uid, d_amount, v_code = sys.argv[1], sys.argv[2], sys.argv[3]
        res = asyncio.run(process_freefire_topup(p_uid, d_amount, v_code))
    else:
        res = json.dumps({"success": False, "reason": "INVALID_PARAMS", "message": "Missing Arguments"})
    
    print(res)