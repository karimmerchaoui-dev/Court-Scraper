import math
import random
import time
from typing import Tuple

from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


class HumanCursorSimulator:
    """
    Simulates realistic human cursor behavior in Selenium WebDriver
    """

    def __init__(self, driver, use_cdp=True):
        self.driver = driver
        self.actions = ActionChains(driver)
        self.current_position = (0, 0)
        self.viewport_size = self._get_viewport_size()
        self.use_cdp = use_cdp

        # Initialize stealth features

    def _get_viewport_size(self) -> Tuple[int, int]:
        """Get the current viewport size"""
        try:
            width = self.driver.execute_script("return window.innerWidth")
            height = self.driver.execute_script("return window.innerHeight")
            return (width, height)
        except:
            return (1920, 1080)  # Default fallback



    def _generate_control_points(self, start, end):
        """
        Generate natural control points for Bezier curve
        Creates a slight curve with randomization for human-like movement
        """
        start_x, start_y = start
        end_x, end_y = end

        # Calculate distance and direction
        distance = math.sqrt((end_x - start_x) ** 2 + (end_y - start_y) ** 2)

        # Control points should be offset perpendicular to the direct line
        # This creates a natural curve

        # First control point (closer to start)
        cp1_progress = random.uniform(0.25, 0.35)  # 25-35% along the path
        cp1_x = start_x + (end_x - start_x) * cp1_progress
        cp1_y = start_y + (end_y - start_y) * cp1_progress

        # Add perpendicular offset for curve
        offset1 = distance * random.uniform(0.1, 0.25)  # 10-25% of distance
        direction1 = random.choice([-1, 1])  # Random curve direction

        # Perpendicular offset
        angle = math.atan2(end_y - start_y, end_x - start_x)
        cp1_x += offset1 * direction1 * math.sin(angle)
        cp1_y += offset1 * direction1 * -math.cos(angle)

        # Second control point (closer to end)
        cp2_progress = random.uniform(0.65, 0.75)  # 65-75% along the path
        cp2_x = start_x + (end_x - start_x) * cp2_progress
        cp2_y = start_y + (end_y - start_y) * cp2_progress

        # Usually curve in same direction, but occasionally opposite for variety
        offset2 = distance * random.uniform(0.05, 0.15)
        direction2 = direction1 if random.random() > 0.2 else -direction1

        cp2_x += offset2 * direction2 * math.sin(angle)
        cp2_y += offset2 * direction2 * -math.cos(angle)

        return [(cp1_x, cp1_y), (cp2_x, cp2_y)]

    def _cubic_bezier_point(self, t, p0, p1, p2, p3):
        """
        Calculate a point on a cubic Bezier curve

        Args:
            t: Parameter from 0 to 1
            p0: Start point (x, y)
            p1: First control point (x, y)
            p2: Second control point (x, y)
            p3: End point (x, y)

        Returns:
            (x, y) point on the curve
        """
        # Cubic Bezier formula: B(t) = (1-t)³P0 + 3(1-t)²tP1 + 3(1-t)t²P2 + t³P3
        u = 1 - t
        tt = t * t
        uu = u * u
        uuu = uu * u
        ttt = tt * t

        x = (uuu * p0[0] +
             3 * uu * t * p1[0] +
             3 * u * tt * p2[0] +
             ttt * p3[0])

        y = (uuu * p0[1] +
             3 * uu * t * p1[1] +
             3 * u * tt * p2[1] +
             ttt * p3[1])

        return (int(x), int(y))
    def _bezier_curve(self, start, end, steps=20, control_points=None):
        """
        Generate points along a Bezier curve for natural mouse movement

        Args:
            start: Tuple (x, y) starting position
            end: Tuple (x, y) ending position
            steps: Number of intermediate points
            control_points: Optional list of control points. If None, they're generated randomly

        Returns:
            List of (x, y) tuples representing the curve path
        """
        if control_points is None:
            # Generate random control points for natural curve
            control_points = self._generate_control_points(start, end)

        points = [start]

        for i in range(1, steps):
            t = i / steps
            point = self._cubic_bezier_point(t, start, control_points[0], control_points[1], end)
            points.append(point)

        points.append(end)
        return points

    def _human_delay(self, min_delay: float = 0.01, max_delay: float = 0.05):
        """Add realistic delay between movements"""
        delay = random.uniform(min_delay, max_delay)
        time.sleep(delay)

    def _get_element_center(self, element) -> Tuple[int, int]:
        """Get the center coordinates of an element relative to viewport"""
        try:
            # Get bounding rectangle relative to viewport
            rect = self.driver.execute_script("""
                const rect = arguments[0].getBoundingClientRect();
                return {
                    x: rect.left + rect.width / 2,
                    y: rect.top + rect.height / 2,
                    inViewport: (
                        rect.top >= 0 &&
                        rect.left >= 0 &&
                        rect.bottom <= window.innerHeight &&
                        rect.right <= window.innerWidth
                    )
                };
            """, element)

            # If not in viewport, scroll it into view
            if not rect['inViewport']:
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({behavior: 'auto', block: 'center'});",
                    element
                )
                time.sleep(0.3)
                # Recalculate after scrolling
                rect = self.driver.execute_script("""
                    const rect = arguments[0].getBoundingClientRect();
                    return {x: rect.left + rect.width / 2, y: rect.top + rect.height / 2};
                """, element)

            return (int(rect['x']), int(rect['y']))
        except Exception as e:
            print(f"Error getting element center: {e}")
            # Fallback
            location = element.location
            size = element.size
            return (location['x'] + size['width'] // 2, location['y'] + size['height'] // 2)
    def _get_element_center_search(self, xpath,driver) -> Tuple[int, int]:
        """Get the center coordinates of an element"""
        element = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, xpath))
        )
        location = element.location
        size = element.size
        center_x = location['x'] + size['width'] // 2
        center_y = location['y'] + size['height'] // 2
        return (center_x, center_y)

    def _add_human_noise(self, x: int, y: int, noise_level: int = 2) -> Tuple[int, int]:
        """Add slight random offset to coordinates to simulate human imprecision"""
        noise_x = random.randint(-noise_level, noise_level)
        noise_y = random.randint(-noise_level, noise_level)
        return (x + noise_x, y + noise_y)

    def move_to_element_naturally_secure(self, element, overshoot=True):
        """
        Move mouse to element with smart security margins that adapt to viewport size
        """
        try:
            self.driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", element)
            time.sleep(random.uniform(0.3, 0.6))

            # Get viewport dimensions
            viewport_width = self.driver.execute_script("return window.innerWidth")
            viewport_height = self.driver.execute_script("return window.innerHeight")

            # Calculate adaptive security margin (5% of viewport size, min 20px, max 100px)
            security_margin = max(20, min(100, int(min(viewport_width, viewport_height) * 0.05)))

            # Define safe area
            safe_min_x = security_margin
            safe_max_x = viewport_width - security_margin
            safe_min_y = security_margin
            safe_max_y = viewport_height - security_margin

            print(f"Safe area: {safe_min_x}-{safe_max_x} x {safe_min_y}-{safe_max_y} (margin: {security_margin}px)")

            target_x, target_y = self._get_element_center(element)

            # If element is outside safe area, adjust our approach
            if (target_x < safe_min_x or target_x > safe_max_x or
                    target_y < safe_min_y or target_y > safe_max_y):
                print("Element near edge - reducing overshoot probability")
                overshoot = False  # Disable overshoot for edge elements

            # Clamp target to safe area
            target_x = max(safe_min_x, min(target_x, safe_max_x))
            target_y = max(safe_min_y, min(target_y, safe_max_y))

            current_x, current_y = self.current_position

            # Add small random offset but keep within safe area
            target_x += random.randint(-3, 3)
            target_y += random.randint(-3, 3)
            target_x = max(safe_min_x, min(target_x, safe_max_x))
            target_y = max(safe_min_y, min(target_y, safe_max_y))

            # Calculate available overshoot space in all directions
            space_left = target_x - safe_min_x
            space_right = safe_max_x - target_x
            space_up = target_y - safe_min_y
            space_down = safe_max_y - target_y

            max_overshoot_x = min(space_left, space_right, 25)  # Don't exceed 25px
            max_overshoot_y = min(space_up, space_down, 25)

            # Only overshoot if we have sufficient space
            if (overshoot and random.random() < 0.3 and
                    max_overshoot_x > 5 and max_overshoot_y > 5):

                overshoot_amount_x = random.uniform(5, max_overshoot_x)
                overshoot_amount_y = random.uniform(5, max_overshoot_y)

                angle = math.atan2(target_y - current_y, target_x - current_x)
                overshoot_x = target_x + int(overshoot_amount_x * math.cos(angle))
                overshoot_y = target_y + int(overshoot_amount_y * math.sin(angle))

                # Clamp to safe area
                overshoot_x = max(safe_min_x, min(overshoot_x, safe_max_x))
                overshoot_y = max(safe_min_y, min(overshoot_y, safe_max_y))

                print(f"Overshooting: {target_x},{target_y} -> {overshoot_x},{overshoot_y}")

                # Move to overshoot point then back to target
                self._move_within_bounds((current_x, current_y), (overshoot_x, overshoot_y),
                                         safe_min_x, safe_max_x, safe_min_y, safe_max_y)
                time.sleep(random.uniform(0.05, 0.1))
                self._move_within_bounds((overshoot_x, overshoot_y), (target_x, target_y),
                                         safe_min_x, safe_max_x, safe_min_y, safe_max_y)
            else:
                # Direct movement
                self._move_within_bounds((current_x, current_y), (target_x, target_y),
                                         safe_min_x, safe_max_x, safe_min_y, safe_max_y)

            self.actions.perform()
            self.actions = ActionChains(self.driver)
            self.current_position = (target_x, target_y)
            time.sleep(random.uniform(0.05, 0.15))

        except Exception as e:
            print(f"Error in natural movement: {e}")
            self.actions.move_to_element(element).perform()
            self.actions = ActionChains(self.driver)

    def _move_within_bounds(self, start, end, min_x, max_x, min_y, max_y, steps=None):
        """Move along curve while staying within specified bounds"""
        if steps is None:
            steps = random.randint(20, 30)

        curve_points = self._bezier_curve(start, end, steps=steps)
        current_x, current_y = start

        for i, (x, y) in enumerate(curve_points[1:]):
            # Enforce security margins
            x = max(min_x, min(x, max_x))
            y = max(min_y, min(y, max_y))

            offset_x = x - current_x
            offset_y = y - current_y

            # Skip tiny movements
            if abs(offset_x) >= 1 or abs(offset_y) >= 1:
                self.actions.move_by_offset(offset_x, offset_y)
                current_x, current_y = x, y

                # Variable speed
                progress = i / len(curve_points)
                if progress < 0.2 or progress > 0.8:
                    self._human_delay(0.003, 0.008)
                else:
                    self._human_delay(0.001, 0.003)

    def move_to_element_naturally_nj(self, xpath, driver, overshoot=True):
        """
        Move mouse to element using Bezier curve with optional overshoot (slower version)
        """
        try:
            element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )

            # ✅ Scroll into view
            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)

            # Now get viewport-relative coordinates
            rect = driver.execute_script("""
                        const rect = arguments[0].getBoundingClientRect();
                        return {x: rect.left + rect.width / 2, y: rect.top + rect.height / 2};
                    """, element)

            target_x, target_y = int(rect['x']), int(rect['y'])
            current_x, current_y = self.current_position

            # Add small random offset to target (humans don't aim for exact center)
            target_x += random.randint(-3, 3)
            target_y += random.randint(-3, 3)

            # Decide if we'll overshoot (30% chance for realism)
            if overshoot and random.random() < 0.3:
                distance = math.sqrt((target_x - current_x) ** 2 + (target_y - current_y) ** 2)
                overshoot_amount = random.uniform(10, 30)

                angle = math.atan2(target_y - current_y, target_x - current_x)
                overshoot_x = target_x + int(overshoot_amount * math.cos(angle))
                overshoot_y = target_y + int(overshoot_amount * math.sin(angle))

                # Increased steps = smoother, slower
                curve_points = self._bezier_curve((current_x, current_y),
                                                  (overshoot_x, overshoot_y),
                                                  steps=random.randint(35, 50))

                for i, (x, y) in enumerate(curve_points[1:]):
                    offset_x = x - current_x
                    offset_y = y - current_y
                    self.actions.move_by_offset(offset_x, offset_y)
                    current_x, current_y = x, y

                    progress = i / len(curve_points)
                    # Slower delays
                    if progress < 0.3 or progress > 0.7:
                        self._human_delay(0.008, 0.015)
                    else:
                        self._human_delay(0.005, 0.010)

                self.actions.perform()
                self.actions = ActionChains(self.driver)
                time.sleep(random.uniform(0.08, 0.18))  # slightly longer pause

                # Correction move (slower too)
                correction_curve = self._bezier_curve((current_x, current_y),
                                                      (target_x, target_y),
                                                      steps=random.randint(15, 25))

                for x, y in correction_curve[1:]:
                    offset_x = x - current_x
                    offset_y = y - current_y
                    self.actions.move_by_offset(offset_x, offset_y)
                    current_x, current_y = x, y
                    self._human_delay(0.006, 0.012)

            else:
                # Direct movement with curve (slower)
                curve_points = self._bezier_curve((current_x, current_y),
                                                  (target_x, target_y),
                                                  steps=random.randint(40, 60))

                for i, (x, y) in enumerate(curve_points[1:]):
                    offset_x = x - current_x
                    offset_y = y - current_y
                    self.actions.move_by_offset(offset_x, offset_y)
                    current_x, current_y = x, y

                    progress = i / len(curve_points)
                    # Slower and smoother delay
                    if progress < 0.2 or progress > 0.8:
                        self._human_delay(0.008, 0.015)
                    else:
                        self._human_delay(0.005, 0.010)

            self.actions.perform()
            self.actions = ActionChains(self.driver)

            # Update current position
            self.current_position = (target_x, target_y)

            # Longer pause after move
            time.sleep(random.uniform(0.1, 0.25))

        except Exception as e:
            print(f"Error in natural movement: {e}")
            element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            self.actions.move_to_element(element).perform()
            self.actions = ActionChains(self.driver)


    def _fallback_click(self, element, offset_x, offset_y, click_type, hold_time):
        """Fallback click using ActionChains"""
        if click_type.lower() == "right":
            self.actions.move_to_element_with_offset(element, offset_x, offset_y)
            self.actions.context_click()
        elif click_type.lower() == "double":
            self.actions.move_to_element_with_offset(element, offset_x, offset_y)
            self.actions.click()
            time.sleep(random.uniform(0.1, 0.2))
            self.actions.click()
        else:
            self.actions.move_to_element_with_offset(element, offset_x, offset_y)
            self.actions.click_and_hold()
            time.sleep(hold_time)
            self.actions.release()

        self.actions.perform()
        self.actions = ActionChains(self.driver)

    def _dispatch_js_mouse_events(self, x, y, event_types=None):
        """
        Dispatch JavaScript mouse events at given coordinates
        More realistic than Selenium's built-in methods
        """
        if event_types is None:
            event_types = ['mousemove']

        script = """
        const x = arguments[0];
        const y = arguments[1];
        const events = arguments[2];
        const element = document.elementFromPoint(x, y) || document.body;

        // Update tracking variables
        window.lastMouseX = x;
        window.lastMouseY = y;
        window.lastMouseMove = Date.now();

        events.forEach(eventType => {
            const event = new MouseEvent(eventType, {
                view: window,
                bubbles: true,
                cancelable: true,
                clientX: x,
                clientY: y,
                screenX: x + window.screenX,
                screenY: y + window.screenY,
                button: 0,
                buttons: eventType.includes('down') ? 1 : 0,
                movementX: Math.random() * 2 - 1,
                movementY: Math.random() * 2 - 1,
                detail: eventType.includes('click') ? 1 : 0
            });
            element.dispatchEvent(event);
        });
        """
        try:
            self.driver.execute_script(script, x, y, event_types)
        except Exception as e:
            print(f"JS event dispatch failed: {e}")
    def human_click(self, element, click_type: str = "left", hold_time: float = None):
        """
        Perform human-like click with realistic timing
        """
        try:
            # Move to element naturally first
            self.move_to_element_naturally(element)

            # Add small random offset for click (humans don't click exactly center)
            click_offset_x = random.randint(-3, 3)
            click_offset_y = random.randint(-3, 3)

            # Pre-click pause (human hesitation)
            time.sleep(random.uniform(0.0175, 0.375))

            if hold_time is None:
                hold_time = random.uniform(0.08, 0.15)  # Realistic click duration

            if click_type.lower() == "right":
                # Right click
                self.actions.move_to_element_with_offset(element, click_offset_x, click_offset_y)
                self.actions.context_click()
                self.actions.context_click()
            elif click_type.lower() == "double":
                # Double click with human timing
                self.actions.move_to_element_with_offset(element, click_offset_x, click_offset_y)
                self.actions.click()
                self.actions.click()
                time.sleep(random.uniform(0.1, 0.2))  # Time between clicks
                self.actions.click()
            else:
                # Regular left click with hold
                self.actions.move_to_element_with_offset(element, click_offset_x, click_offset_y)
                self.actions.click_and_hold()
                time.sleep(hold_time)
                self.actions.release()
                self.actions.perform()
            self.actions = ActionChains(self.driver)

            # Post-click pause
            time.sleep(random.uniform(0.05, 0.15))
        except StaleElementReferenceException:
            print("stale")
            element.click()
            return
        except Exception as e:
            # Fallback to regular click
            element.click()

    def _cdp_mouse_move(self, x, y):
        """Use Chrome DevTools Protocol for genuine mouse movement"""
        if not self.cdp_available:
            return False

        try:
            self.driver.execute_cdp_cmd('Input.dispatchMouseEvent', {
                'type': 'mouseMoved',
                'x': x,
                'y': y,
                'button': 'none',
                'clickCount': 0
            })
            return True
        except Exception as e:
            print(f"CDP mouse move failed: {e}")
            return False

    def _cdp_mouse_click(self, x, y, button='left'):
        """Use CDP for realistic mouse click"""
        if not self.cdp_available:
            return False

        try:
            # Move to position
            self._cdp_mouse_move(x, y)
            time.sleep(random.uniform(0.05, 0.12))

            # Mouse down
            self.driver.execute_cdp_cmd('Input.dispatchMouseEvent', {
                'type': 'mousePressed',
                'x': x,
                'y': y,
                'button': button,
                'clickCount': 1
            })
            time.sleep(random.uniform(0.08, 0.15))

            # Mouse up
            self.driver.execute_cdp_cmd('Input.dispatchMouseEvent', {
                'type': 'mouseReleased',
                'x': x,
                'y': y,
                'button': button,
                'clickCount': 1
            })
            return True
        except Exception as e:
            print(f"CDP click failed: {e}")
            return False

    def human_click_nj(self, xpath,driver,click_type: str = "left", hold_time: float = None):
        """
        Perform human-like click with realistic timing
        """
        try:
            # Move to element naturally first
            self.move_to_element_naturally_nj(xpath,driver)
            element = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, xpath))
            )
            # Add small random offset for click (humans don't click exactly center)
            click_offset_x = random.randint(-3, 3)
            click_offset_y = random.randint(-3, 3)

            # Pre-click pause (human hesitation)
            time.sleep(random.uniform(0.00875, 0.1875))

            if hold_time is None:
                hold_time = random.uniform(0.08, 0.15)  # Realistic click duration

            if click_type.lower() == "right":
                # Right click
                self.actions.move_to_element_with_offset(element, click_offset_x, click_offset_y)
                self.actions.context_click()
                self.actions.context_click()
            elif click_type.lower() == "double":
                # Double click with human timing
                self.actions.move_to_element_with_offset(element, click_offset_x, click_offset_y)
                self.actions.click()
                self.actions.click()
                time.sleep(random.uniform(0.1, 0.2))  # Time between clicks
                self.actions.click()
            else:
                # Regular left click with hold
                self.actions.move_to_element_with_offset(element, click_offset_x, click_offset_y)
                self.actions.click_and_hold()
                time.sleep(hold_time)
                self.actions.release()
                self.actions.perform()
            self.actions = ActionChains(self.driver)

            # Post-click pause
            time.sleep(random.uniform(0.05, 0.15))
        except StaleElementReferenceException:
            print("stale")
            element.click()
            return
        except Exception as e:
            # Fallback to regular click
            element.click()
    def _get_element_text_content(self, element) -> str:
        """Get the current text content of an element"""
        try:
            # Try different ways to get text content
            text = element.get_attribute('value')  # For input fields
            if text is None or text == '':
                text = element.text  # For other elements
            if text is None:
                text = ''
            return text.strip()
        except:
            return ''

    def _triple_click_select(self, element):
        """Simulate triple-click to select all text (common human behavior)"""
        try:
            # Move to element center with slight randomization
            center_x, center_y = self._get_element_center(element)
            offset_x = random.randint(-5, 5)
            offset_y = random.randint(-2, 2)

            # Perform triple click with human timing
            self.actions.move_to_element_with_offset(element, offset_x, offset_y)

            # First click
            self.actions.click()
            time.sleep(random.uniform(0.05, 0.15))

            # Second click (double-click timing)
            self.actions.click()
            time.sleep(random.uniform(0.05, 0.12))

            # Third click
            self.actions.click()

            self.actions.perform()
            self.actions = ActionChains(self.driver)

        except Exception as e:
            print(f"Error in triple click: {e}")
            # Fallback to double click
            self.actions.double_click(element).perform()
            self.actions = ActionChains(self.driver)
    def human_clear_input(self, element, clear_method: str = "auto"):
        """
        Clear input field in a human-like manner, only if there's text present

        Args:
            element: The input element to clear
            clear_method: "auto", "select_all", "backspace", "ctrl_a"
        """
        try:
            # Check if there's any text to clear
            current_text = self._get_element_text_content(element)
            if not current_text:
                return  # Nothing to clear

            print(f"Clearing text: '{current_text}' (length: {len(current_text)})")

            # Click on the element first to focus it
            self.human_click(element)
            time.sleep(random.uniform(0.1, 0.3))

            # Choose clearing method
            if clear_method == "auto":
                # Randomly choose a method based on text length
                if len(current_text) > 20:
                    clear_method = random.choice(["select_all", "ctrl_a"])
                elif len(current_text) > 5:
                    clear_method = random.choice(["select_all", "backspace", "ctrl_a"])
                else:
                    clear_method = random.choice(["backspace", "select_all"])

            if clear_method == "ctrl_a":
                # Ctrl+A to select all, then type
                element.send_keys(Keys.CONTROL + "a")
                time.sleep(random.uniform(0.1, 0.3))
                element.send_keys(Keys.DELETE)

            elif clear_method == "select_all":
                # Triple click to select all (common human behavior)
                self._triple_click_select(element)
                time.sleep(random.uniform(0.1, 0.2))
                element.send_keys(Keys.DELETE)

            elif clear_method == "backspace":
                # Human-like backspacing
                self._human_backspace_clear(element, len(current_text))

            # Small pause after clearing
            time.sleep(random.uniform(0.1, 0.4))

        except StaleElementReferenceException:
            print("Element became stale during clear operation")
            return
        except Exception as e:
            print(f"Error in human clear: {e}")
            # Fallback to standard clear
            try:
                element.clear()
            except:
                pass

    def _human_backspace_clear(self, element, text_length: int):
        """Clear text using backspace key with human-like timing"""
        try:
            # Move cursor to end of text first (humans often do this)
            element.send_keys(Keys.END)
            time.sleep(random.uniform(0.05, 0.15))

            # Backspace with human-like timing and occasional pauses
            for i in range(text_length):
                element.send_keys(Keys.BACKSPACE)

                # Variable timing - sometimes faster, sometimes slower
                if i % random.randint(3, 7) == 0:
                    # Occasional longer pause (like thinking or looking at screen)
                    time.sleep(random.uniform(0.2, 0.5))
                else:
                    # Normal backspace timing
                    if random.random() < 0.1:
                        # Sometimes very quick
                        time.sleep(random.uniform(0.02, 0.05))
                    else:
                        # Normal timing
                        time.sleep(random.uniform(0.08, 0.15))

                # Occasionally pause and resume (human behavior)
                if random.random() < 0.05:
                    time.sleep(random.uniform(0.3, 0.8))

        except Exception as e:
            print(f"Error in backspace clear: {e}")

    def human_type(self, element, text: str, typing_speed: str = "normal",
                   clear_first: bool = True, clear_method: str = "auto"):
        """Type text with human-like irregular rhythm, typos, and ~50% slower speed."""
        try:
            # -------------------------
            # CLEAR FIELD FIRST
            # -------------------------
            if clear_first:
                self.human_clear_input(element, clear_method)
                element.clear()
                time.sleep(random.uniform(0.08, 0.95))  # slower clear delay

            # -------------------------
            # BASE SPEEDS (already slowed ~50%)
            # -------------------------
            if typing_speed == "fast":
                base_min, base_max = 0.04, 0.55
            elif typing_speed == "slow":
                base_min, base_max = 0.11, 0.32
            else:  # normal
                base_min, base_max = 0.028, 0.065

            # -------------------------
            # CONFIG
            # -------------------------
            typo_chance = 0.045  # slightly higher for realism
            burst_chance = 0.10  # sometimes humans type faster for 1–3 chars
            long_pause_chance = 0.06  # stop typing for a moment
            wrong_chars = "abcdefghijklmnopqrstuvwxyz"

            burst_active = False
            burst_remaining = 0

            for i, char in enumerate(text):

                # ---------- TYPO SIMULATION ----------
                if i > 1 and random.random() < typo_chance:
                    wrong = random.choice(wrong_chars)
                    element.send_keys(wrong)

                    time.sleep(random.uniform(0.25, 0.55))  # pause after mistake
                    element.send_keys("\b")  # delete
                    time.sleep(random.uniform(0.12, 0.22))  # re-think delay

                # ---------- SEND REAL CHAR ----------
                element.send_keys(char)

                # ---------- BURST MODE ----------
                if not burst_active and random.random() < burst_chance:
                    burst_active = True
                    burst_remaining = random.randint(1, 3)

                if burst_active:
                    delay = random.uniform(base_min * 0.4, base_min * 0.8)
                    burst_remaining -= 1
                    if burst_remaining <= 0:
                        burst_active = False

                else:
                    # Normal variable delay
                    if char in (' ', '.', ',', '?', '!'):
                        delay = random.uniform(base_min * 1.5, base_max * 1.5)
                    else:
                        delay = random.uniform(base_min, base_max)

                # ---------- LONG "THINKING" PAUSE ----------
                if random.random() < long_pause_chance:
                    delay += random.uniform(0.2, 0.55)

                time.sleep(delay)

            # Final slight pause
            time.sleep(random.uniform(0.12, 0.40))

        except StaleElementReferenceException:
            pass
        except Exception as e:
            print(f"[Typing Error] {e}")
            element.clear()
            element.send_keys(text)

    def human_scroll(self, direction: str = "down", amount: int = 3, smooth: bool = True):
        """
        Perform human-like scrolling
        """
        try:
            if smooth:
                # Smooth scrolling with multiple small movements
                scroll_steps = random.randint(3, 7)
                total_scroll = amount * 120  # Approximate scroll amount
                step_size = total_scroll // scroll_steps

                for _ in range(scroll_steps):
                    if direction.lower() == "up":
                        self.driver.execute_script(f"window.scrollBy(0, -{step_size})")
                    else:  # down
                        self.driver.execute_script(f"window.scrollBy(0, {step_size})")

                    # Random delay between scroll steps
                    time.sleep(random.uniform(0.05, 0.15))
            else:
                # Single scroll action
                scroll_amount = amount * 120
                if direction.lower() == "up":
                    self.driver.execute_script(f"window.scrollBy(0, -{scroll_amount})")
                else:
                    self.driver.execute_script(f"window.scrollBy(0, {scroll_amount})")

            # Pause after scrolling
            time.sleep(random.uniform(0.3, 0.7))

        except Exception as e:
            print(f"Error in human scrolling: {e}")

    def human_hover(self, element, hover_time: float = None):
        """
        Hover over element with human-like behavior
        """
        try:
            if hover_time is None:
                hover_time = random.uniform(0.5, 2.0)

            # Move to element naturally
            self.move_to_element_naturally(element)

            # Small movements while hovering (humans don't keep cursor perfectly still)
            start_time = time.time()
            while time.time() - start_time < hover_time:
                # Small random movements
                offset_x = random.randint(-2, 2)
                offset_y = random.randint(-2, 2)

                self.actions.move_by_offset(offset_x, offset_y)
                self.actions.perform()
                self.actions = ActionChains(self.driver)

                time.sleep(random.uniform(0.1, 0.3))

        except Exception as e:
            print(f"Error in human hover: {e}")

    def simulate_reading_behavior(self, duration: float = None):
        """
        Simulate human reading behavior with random mouse movements
        """
        if duration is None:
            duration = random.uniform(2.0, 8.0)

        start_time = time.time()
        while time.time() - start_time < duration:
            # Random small movements to simulate reading
            viewport_width, viewport_height = self.viewport_size

            # Move to random positions on the page
            target_x = random.randint(100, viewport_width - 100)
            target_y = random.randint(100, viewport_height - 100)

            # Move cursor to random position
            current_x, current_y = self.current_position
            offset_x = target_x - current_x
            offset_y = target_y - current_y

            self.actions.move_by_offset(offset_x, offset_y)
            self.actions.perform()
            self.actions = ActionChains(self.driver)

            self.current_position = (target_x, target_y)

            # Pause like reading
            time.sleep(random.uniform(0.5, 2.0))

    def human_drag_and_drop(self, source_element, target_element):
        """
        Perform human-like drag and drop operation
        """
        try:
            # Move to source element
            self.move_to_element_naturally(source_element)
            time.sleep(random.uniform(0.2, 0.4))

            # Click and hold
            self.actions.click_and_hold(source_element)
            self.actions.perform()
            time.sleep(random.uniform(0.1, 0.3))

            # Get target position
            target_x, target_y = self._get_element_center(target_element)
            current_x, current_y = self.current_position

            # Generate curve for drag movement
            curve_points = self._bezier_curve((current_x, current_y), (target_x, target_y), steps=15)

            # Drag along curve
            for i, (x, y) in enumerate(curve_points[1:]):  # Skip first point
                offset_x = x - current_x
                offset_y = y - current_y

                self.actions.move_by_offset(offset_x, offset_y)
                current_x, current_y = x, y

                # Slower movement during drag
                self._human_delay(0.02, 0.08)

            # Release at target
            self.actions.release(target_element)
            self.actions.perform()
            self.actions = ActionChains(self.driver)

            # Update position
            self.current_position = (target_x, target_y)

            # Pause after drop
            time.sleep(random.uniform(0.3, 0.6))

        except Exception as e:
            print(f"Error in drag and drop: {e}")
            # Fallback to standard drag and drop
            ActionChains(self.driver).drag_and_drop(source_element, target_element).perform()





def enhanced_human_like_attention(driver):
    """
    Enhanced version of your human_like_attention function
    """
    human_cursor = HumanCursorSimulator(driver)
    human_cursor.simulate_reading_behavior(duration=random.uniform(1.0, 3.0))


# Browser-level cursor injection (Advanced)
def inject_realistic_cursor_js(driver):
    """
    Inject JavaScript to show and control a realistic cursor at a random position
    """
    cursor_js = """
    // Create custom cursor
    if (!document.getElementById('human-cursor')) {
        var cursor = document.createElement('div');
        cursor.id = 'human-cursor';

        // Generate random initial position
        var randomX = Math.floor(Math.random() * (window.innerWidth - 20));
        var randomY = Math.floor(Math.random() * (window.innerHeight - 20));

        cursor.style.cssText = `
            position: fixed;
            width: 20px;
            height: 20px;
            left: ${randomX}px;
            top: ${randomY}px;
            background: url('data:image/svg+xml;utf8,<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24"><path fill="black" d="M13.64,21.97C13.14,22.21 12.54,22 12.31,21.5L10.13,16.76L7.62,18.78C7.45,18.92 7.24,19 7,19A1,1 0 0,1 6,18V3A1,1 0 0,1 7,2C7.24,2 7.47,2.09 7.64,2.27L7.65,2.28L19.14,11.86C19.57,12.22 19.62,12.85 19.27,13.27C19.12,13.45 18.91,13.57 18.7,13.61L15.54,14.23L17.74,18.96C18,19.46 17.76,20.05 17.26,20.28L13.64,21.97Z"/></svg>') no-repeat center center;
            background-size: contain;
            pointer-events: none;
            z-index: 999999;
            transition: all 0.1s ease-out;
        `;
        document.body.appendChild(cursor);

        // Hide default cursor
        document.body.style.cursor = 'none';

        // Update cursor position
        window.updateCursorPosition = function(x, y) {
            cursor.style.left = x + 'px';
            cursor.style.top = y + 'px';
        };
    }
    """

    try:
        driver.execute_script(cursor_js)
    except Exception as e:
        print(f"Could not inject cursor JavaScript: {e}")


def update_cursor_position(driver, x, y):
    """
    Update the visual cursor position in the browser
    """
    try:
        driver.execute_script(f"window.updateCursorPosition && window.updateCursorPosition({x}, {y});")
    except:
        pass