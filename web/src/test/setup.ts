import "@testing-library/jest-dom/vitest";

// jsdom lacks <dialog> methods
HTMLDialogElement.prototype.showModal = function () {
  this.open = true;
};
HTMLDialogElement.prototype.close = function () {
  this.open = false;
};
