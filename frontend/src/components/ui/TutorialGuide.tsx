'use client'

import React, { useState, useEffect, useRef } from 'react';
import { X, ChevronRight, ChevronLeft } from 'lucide-react';

export interface TutorialStep {
  targetId: string;
  title: string;
  description: string;
  position?: 'top' | 'bottom' | 'left' | 'right';
}

interface TutorialGuideProps {
  steps: TutorialStep[];
  onComplete?: () => void;
}

interface HighlightPosition {
  top: number;
  left: number;
  width: number;
  height: number;
}

const TutorialGuide: React.FC<TutorialGuideProps> = ({ steps, onComplete }) => {
  const [isActive, setIsActive] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);
  const [highlightPos, setHighlightPos] = useState<HighlightPosition | null>(null);
  const tooltipRef = useRef<HTMLDivElement>(null);

  const step = steps[currentStep];

  useEffect(() => {
    if (!isActive || !step) return;

    const updateHighlight = () => {
      const element = document.getElementById(step.targetId);
      if (element) {
        const rect = element.getBoundingClientRect();
        setHighlightPos({
          top: rect.top + window.scrollY,
          left: rect.left + window.scrollX,
          width: rect.width,
          height: rect.height,
        });

        // Scroll vào view
        element.scrollIntoView({ behavior: 'smooth', block: 'center' });
      } else {
        console.warn(`Element with ID "${step.targetId}" not found`);
      }
    };

    // Delay slightly để đảm bảo DOM đã ready
    const timer = setTimeout(updateHighlight, 100);
    
    const handleResize = () => {
      updateHighlight();
    };
    
    const handleScroll = () => {
      updateHighlight();
    };

    window.addEventListener('resize', handleResize);
    window.addEventListener('scroll', handleScroll);
    
    // MutationObserver để theo dõi thay đổi DOM (nếu element resize)
    const observer = new MutationObserver(() => {
      updateHighlight();
    });
    
    const element = document.getElementById(step.targetId);
    if (element) {
      observer.observe(element, {
        attributes: true,
        attributeFilter: ['style', 'class'],
        subtree: true,
      });
    }
    
    return () => {
      clearTimeout(timer);
      window.removeEventListener('resize', handleResize);
      window.removeEventListener('scroll', handleScroll);
      observer.disconnect();
    };
  }, [isActive, step, currentStep]);

  const getTooltipPosition = (): React.CSSProperties => {
    if (!highlightPos || !tooltipRef.current) return {};

    const offset = 20;
    const PADDING = 16; // Padding từ cạnh màn hình
    
    // Get actual tooltip dimensions from DOM
    const tooltipElement = tooltipRef.current;
    const TOOLTIP_WIDTH = tooltipElement?.offsetWidth || 320;
    const TOOLTIP_HEIGHT = tooltipElement?.offsetHeight || 320;
    
    // Viewport dimensions
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;

    // Calculate available space in each direction
    const spaceTop = highlightPos.top - PADDING;
    const spaceBottom = viewportHeight - (highlightPos.top + highlightPos.height) - PADDING;
    const spaceLeft = highlightPos.left - PADDING;
    const spaceRight = viewportWidth - (highlightPos.left + highlightPos.width) - PADDING;

    // Determine best position based on available space
    let position = 'bottom';
    let top = 0;
    let left = 0;
    let transform = 'translate(-50%, 0)';

    // Try bottom first
    if (spaceBottom >= TOOLTIP_HEIGHT) {
      position = 'bottom';
      top = highlightPos.top + highlightPos.height + offset;
      left = highlightPos.left + highlightPos.width / 2;
      transform = 'translate(-50%, 0)';
    }
    // Try top
    else if (spaceTop >= TOOLTIP_HEIGHT) {
      position = 'top';
      top = highlightPos.top - offset;
      left = highlightPos.left + highlightPos.width / 2;
      transform = 'translate(-50%, -100%)';
    }
    // Try right
    else if (spaceRight >= TOOLTIP_WIDTH) {
      position = 'right';
      top = highlightPos.top + highlightPos.height / 2;
      left = highlightPos.left + highlightPos.width + offset;
      transform = 'translate(0, -50%)';
    }
    // Try left
    else if (spaceLeft >= TOOLTIP_WIDTH) {
      position = 'left';
      top = highlightPos.top + highlightPos.height / 2;
      left = highlightPos.left - offset;
      transform = 'translate(-100%, -50%)';
    }
    // Fallback: position at center bottom with adjustments
    else {
      position = 'center-bottom';
      top = highlightPos.top + highlightPos.height + offset;
      left = highlightPos.left + highlightPos.width / 2;
      transform = 'translate(-50%, 0)';
    }

    // Ensure tooltip doesn't go outside viewport horizontally
    let adjustedLeft = left;
    if (position === 'bottom' || position === 'top' || position === 'center-bottom') {
      const tooltipLeft = left - TOOLTIP_WIDTH / 2;
      const tooltipRight = tooltipLeft + TOOLTIP_WIDTH;
      
      if (tooltipLeft < PADDING) {
        adjustedLeft = PADDING + TOOLTIP_WIDTH / 2;
      } else if (tooltipRight > viewportWidth - PADDING) {
        adjustedLeft = viewportWidth - PADDING - TOOLTIP_WIDTH / 2;
      }
    } else if (position === 'right') {
      const tooltipRight = left + TOOLTIP_WIDTH;
      if (tooltipRight > viewportWidth - PADDING) {
        adjustedLeft = viewportWidth - PADDING - TOOLTIP_WIDTH;
      }
    } else if (position === 'left') {
      if (left - TOOLTIP_WIDTH < PADDING) {
        adjustedLeft = PADDING;
      }
    }

    // Ensure tooltip doesn't go outside viewport vertically
    let adjustedTop = top;
    if (position === 'right' || position === 'left') {
      const tooltipTop = top - TOOLTIP_HEIGHT / 2;
      const tooltipBottom = tooltipTop + TOOLTIP_HEIGHT;
      
      if (tooltipTop < PADDING) {
        adjustedTop = PADDING + TOOLTIP_HEIGHT / 2;
      } else if (tooltipBottom > viewportHeight - PADDING) {
        adjustedTop = viewportHeight - PADDING - TOOLTIP_HEIGHT / 2;
      }
    } else {
      if (top + TOOLTIP_HEIGHT > viewportHeight - PADDING) {
        // If bottom doesn't fit and we're already in bottom position, try top
        if (position === 'center-bottom' || position === 'bottom') {
          if (spaceTop >= TOOLTIP_HEIGHT) {
            adjustedTop = highlightPos.top - offset;
            transform = 'translate(-50%, -100%)';
          } else {
            // As last resort, position inside viewport
            adjustedTop = viewportHeight - PADDING - TOOLTIP_HEIGHT;
          }
        }
      }
    }

    return {
      top: adjustedTop,
      left: adjustedLeft,
      transform,
    };
  };

  const handleNext = () => {
    if (currentStep < steps.length - 1) {
      setCurrentStep(currentStep + 1);
    } else {
      handleComplete();
    }
  };

  const handlePrev = () => {
    if (currentStep > 0) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleComplete = () => {
    setIsActive(false);
    setCurrentStep(0);
    onComplete?.();
  };

  if (!isActive) {
    return (
      <button
        onClick={() => setIsActive(true)}
        className="fixed bottom-8 right-8 z-40 flex items-center justify-center w-12 h-12 bg-gradient-to-r from-blue-500 to-purple-600 text-white rounded-full shadow-lg hover:shadow-xl hover:from-blue-600 hover:to-purple-700 transition-all duration-300 hover:scale-110"
        title="Hướng dẫn sử dụng"
      >
        <span className="text-lg font-bold">?</span>
      </button>
    );
  }

  return (
    <>
      {/* Overlay */}
      <div
        className="fixed inset-0 z-40 bg-black/50 pointer-events-auto"
        onClick={handleComplete}
      >
        {/* Highlight spotlight */}
        {highlightPos && (
          <div
            className="absolute border-4 border-yellow-400 rounded-lg shadow-2xl transition-all duration-300"
            style={{
              top: highlightPos.top - 8,
              left: highlightPos.left - 8,
              width: highlightPos.width + 16,
              height: highlightPos.height + 16,
              boxShadow: '0 0 0 9999px rgba(0, 0, 0, 0.5), 0 0 20px rgba(250, 204, 21, 0.4)',
              pointerEvents: 'none',
            }}
          />
        )}
      </div>

      {/* Tooltip */}
      <div
        ref={tooltipRef}
        className="fixed z-50 bg-white rounded-xl shadow-2xl max-w-sm pointer-events-auto border border-gray-100"
        style={getTooltipPosition()}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Tooltip content */}
        <div className="p-6">
          {/* Header */}
          <div className="flex items-start justify-between mb-4 gap-2">
            <div className="flex-1">
              <h3 className="text-lg font-bold text-gray-800 leading-tight">
                {step?.title}
              </h3>
              <p className="text-xs text-gray-500 mt-1">
                Bước {currentStep + 1} / {steps.length}
              </p>
            </div>
            <button
              onClick={handleComplete}
              className="text-gray-400 hover:text-gray-600 transition-colors flex-shrink-0 mt-1"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Description */}
          <p className="text-sm text-gray-700 mb-6 leading-relaxed line-clamp-4">
            {step?.description}
          </p>

          {/* Progress bar */}
          <div className="w-full h-1 bg-gray-200 rounded-full mb-6 overflow-hidden">
            <div
              className="h-full bg-gradient-to-r from-blue-500 to-purple-600 transition-all duration-300"
              style={{ width: `${((currentStep + 1) / steps.length) * 100}%` }}
            />
          </div>

          {/* Footer buttons */}
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <button
              onClick={handlePrev}
              disabled={currentStep === 0}
              className="flex items-center gap-1 px-3 py-2 text-xs sm:text-sm text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200 disabled:opacity-50 disabled:cursor-not-allowed transition-colors whitespace-nowrap"
            >
              <ChevronLeft className="w-3 h-3 sm:w-4 sm:h-4" />
              <span className="hidden sm:inline font-medium">Trước</span>
            </button>

            <div className="flex gap-1 flex-1 justify-center">
              {steps.map((_, index) => (
                <button
                  key={index}
                  onClick={() => setCurrentStep(index)}
                  className={`transition-all ${
                    index === currentStep
                      ? 'bg-gradient-to-r from-blue-500 to-purple-600 w-6 h-2'
                      : 'bg-gray-300 hover:bg-gray-400 w-2 h-2'
                  } rounded-full`}
                  title={`Bước ${index + 1}`}
                />
              ))}
            </div>

            <button
              onClick={currentStep === steps.length - 1 ? handleComplete : handleNext}
              className="flex items-center gap-1 px-3 py-2 text-xs sm:text-sm text-white bg-gradient-to-r from-blue-500 to-purple-600 rounded-lg hover:from-blue-600 hover:to-purple-700 transition-colors whitespace-nowrap"
            >
              <span className="font-medium">
                {currentStep === steps.length - 1 ? 'Xong' : 'Tiếp'}
              </span>
              {currentStep !== steps.length - 1 && <ChevronRight className="w-3 h-3 sm:w-4 sm:h-4" />}
            </button>
          </div>

          {/* Skip button */}
          <button
            onClick={handleComplete}
            className="w-full mt-4 text-xs text-gray-500 hover:text-gray-700 transition-colors py-1"
          >
            Bỏ qua hướng dẫn
          </button>
        </div>
      </div>
    </>
  );
};

export default TutorialGuide;
