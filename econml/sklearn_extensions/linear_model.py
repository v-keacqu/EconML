# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.

"""Collection of scikit-learn extensions for linear models."""

import numbers
import numpy as np
import warnings
from collections.abc import Iterable
from scipy.stats import norm
from econml.sklearn_extensions.model_selection import WeightedKFold, WeightedStratifiedKFold
from sklearn.linear_model import LassoCV, MultiTaskLassoCV, Lasso, MultiTaskLasso
from sklearn.model_selection import KFold, StratifiedKFold
from sklearn.model_selection._split import _CVIterableWrapper, CV_WARNING
from sklearn.multioutput import MultiOutputRegressor
from sklearn.utils import check_array, check_X_y
from sklearn.utils.multiclass import type_of_target


def _fit_weighted_linear_model(self, class_name, X, y, sample_weight, check_input=None):
    # Convert X, y into numpy arrays
    X, y = check_X_y(X, y, y_numeric=True, multi_output=True)
    # Define fit parameters
    fit_params = {'X': X, 'y': y}
    # Some algorithms doen't have a check_input option
    if check_input is not None:
        fit_params['check_input'] = check_input

    if sample_weight is not None:
        # Check weights array
        if np.atleast_1d(sample_weight).ndim > 1:
            # Check that weights are size-compatible
            raise ValueError("Sample weights must be 1D array or scalar")
        if np.ndim(sample_weight) == 0:
            sample_weight = np.repeat(sample_weight, X.shape[0])
        else:
            sample_weight = check_array(sample_weight, ensure_2d=False, allow_nd=False)
            if sample_weight.shape[0] != X.shape[0]:
                raise ValueError(
                    "Found array with {0} sample(s) while {1} samples were expected.".format(
                        sample_weight.shape[0], X.shape[0])
                )

        # Normalize inputs
        X, y, X_offset, y_offset, X_scale = self._preprocess_data(
            X, y, fit_intercept=self.fit_intercept, normalize=False,
            copy=self.copy_X, check_input=check_input if check_input is not None else True,
            sample_weight=sample_weight, return_mean=True)
        # Weight inputs
        normalized_weights = X.shape[0] * sample_weight / np.sum(sample_weight)
        sqrt_weights = np.sqrt(normalized_weights)
        weight_mat = np.diag(sqrt_weights)
        X_weighted = np.matmul(weight_mat, X)
        y_weighted = np.matmul(weight_mat, y)
        fit_params['X'] = X_weighted
        fit_params['y'] = y_weighted
        if self.fit_intercept:
            # Fit base class without intercept
            self.fit_intercept = False
            # Fit Lasso
            super(class_name, self).fit(**fit_params)
            # Reset intercept
            self.fit_intercept = True
            # The intercept is not calculated properly due the sqrt(weights) factor
            # so it must be recomputed
            self._set_intercept(X_offset, y_offset, X_scale)
        else:
            super(class_name, self).fit(**fit_params)
    else:
        # Fit lasso without weights
        super(class_name, self).fit(**fit_params)


def _weighted_check_cv(cv='warn', y=None, classifier=False):
    if cv is None or cv == 'warn':
        warnings.warn(CV_WARNING, FutureWarning)
        cv = 3

    if isinstance(cv, numbers.Integral):
        if (classifier and (y is not None) and
                (type_of_target(y) in ('binary', 'multiclass'))):
            return WeightedStratifiedKFold(cv)
        else:
            return WeightedKFold(cv)

    if not hasattr(cv, 'split') or isinstance(cv, str):
        if not isinstance(cv, Iterable) or isinstance(cv, str):
            raise ValueError("Expected cv as an integer, cross-validation "
                             "object (from sklearn.model_selection) "
                             "or an iterable. Got %s." % cv)
        return _WeightedCVIterableWrapper(cv)

    return cv  # New style cv objects are passed without any modification


class _WeightedCVIterableWrapper(_CVIterableWrapper):
    def __init__(self, cv):
        super().__init__(cv)

    def get_n_splits(self, X=None, y=None, groups=None, sample_weight=None):
        return super().get_n_splits(self, X, y, groups)

    def split(self, X=None, y=None, groups=None, sample_weight=None):
        return super().split(X, y, groups)


class WeightedLasso(Lasso):
    """Version of sklearn Lasso that accepts weights.

    Parameters
    ----------
    alpha : float, optional
        Constant that multiplies the L1 term. Defaults to 1.0.
        ``alpha = 0`` is equivalent to ordinary least squares, solved
        by the :class:`LinearRegression` object. For numerical
        reasons, using ``alpha = 0`` with Lasso is not advised.
        Given this, you should use the :class:`LinearRegression` object.

    fit_intercept : boolean, optional, default True
        Whether to calculate the intercept for this model. If set
        to False, no intercept will be used in calculations
        (e.g. data is expected to be already centered).

    precompute : True | False | array-like, default=False
        Whether to use a precomputed Gram matrix to speed up
        calculations. If set to ``'auto'`` let us decide. The Gram
        matrix can also be passed as argument. For sparse input
        this option is always ``True`` to preserve sparsity.

    copy_X : boolean, optional, default True
        If ``True``, X will be copied; else, it may be overwritten.

    max_iter : int, optional
        The maximum number of iterations

    tol : float, optional
        The tolerance for the optimization: if the updates are
        smaller than ``tol``, the optimization code checks the
        dual gap for optimality and continues until it is smaller
        than ``tol``.

    warm_start : bool, optional
        When set to True, reuse the solution of the previous call to fit as
        initialization, otherwise, just erase the previous solution.
        See :term:`the Glossary <warm_start>`.

    positive : bool, optional
        When set to ``True``, forces the coefficients to be positive.

    random_state : int, RandomState instance or None, optional, default None
        The seed of the pseudo random number generator that selects a random
        feature to update.  If int, random_state is the seed used by the random
        number generator; If RandomState instance, random_state is the random
        number generator; If None, the random number generator is the
        RandomState instance used by `np.random`. Used when ``selection`` ==
        'random'.

    selection : str, default 'cyclic'
        If set to 'random', a random coefficient is updated every iteration
        rather than looping over features sequentially by default. This
        (setting to 'random') often leads to significantly faster convergence
        especially when tol is higher than 1e-4.

    Attributes
    ----------
    coef_ : array, shape (n_features,) | (n_targets, n_features)
        parameter vector (w in the cost function formula)

    sparse_coef_ : scipy.sparse matrix, shape (n_features, 1) | (n_targets, n_features)
        ``sparse_coef_`` is a readonly property derived from ``coef_``

    intercept_ : float | array, shape (n_targets,)
        independent term in decision function.

    n_iter_ : int | array-like, shape (n_targets,)
        number of iterations run by the coordinate descent solver to reach
        the specified tolerance.
    """

    def __init__(self, alpha=1.0, fit_intercept=True,
                 precompute=False, copy_X=True, max_iter=1000,
                 tol=1e-4, warm_start=False, positive=False,
                 random_state=None, selection='cyclic'):
        super().__init__(
            alpha=alpha, fit_intercept=fit_intercept,
            normalize=False, precompute=precompute, copy_X=copy_X,
            max_iter=max_iter, tol=tol, warm_start=warm_start,
            positive=positive, random_state=random_state,
            selection=selection)

    def fit(self, X, y, sample_weight=None, check_input=True):
        """Fit model with coordinate descent.

        Parameters
        ----------
        X : ndarray or scipy.sparse matrix, (n_samples, n_features)
            Data

        y : ndarray, shape (n_samples,) or (n_samples, n_targets)
            Target. Will be cast to X's dtype if necessary

        sample_weight : numpy array of shape [n_samples]
                        Individual weights for each sample.
                        The weights will be normalized internally.

        check_input : boolean, (default=True)
            Allow to bypass several input checking.
            Don't use this parameter unless you know what you do.
        """
        _fit_weighted_linear_model(self, WeightedLasso, X, y, sample_weight, check_input)
        return self


class WeightedMultiTaskLasso(MultiTaskLasso):
    """Version of sklearn MultiTaskLasso that accepts weights.

    Parameters
    ----------
    alpha : float, optional
        Constant that multiplies the L1 term. Defaults to 1.0.
        ``alpha = 0`` is equivalent to an ordinary least square, solved
        by the :class:`LinearRegression` object. For numerical
        reasons, using ``alpha = 0`` with the ``Lasso`` object is not advised.
        Given this, you should use the :class:`LinearRegression` object.

    fit_intercept : boolean, optional, default True
        Whether to calculate the intercept for this model. If set
        to False, no intercept will be used in calculations
        (e.g. data is expected to be already centered).

    copy_X : boolean, optional, default True
        If ``True``, X will be copied; else, it may be overwritten.

    max_iter : int, optional
        The maximum number of iterations

    tol : float, optional
        The tolerance for the optimization: if the updates are
        smaller than ``tol``, the optimization code checks the
        dual gap for optimality and continues until it is smaller
        than ``tol``.

    warm_start : bool, optional
        When set to True, reuse the solution of the previous call to fit as
        initialization, otherwise, just erase the previous solution.
        See :term:`the Glossary <warm_start>`.

    random_state : int, RandomState instance or None, optional, default None
        The seed of the pseudo random number generator that selects a random
        feature to update.  If int, random_state is the seed used by the random
        number generator; If RandomState instance, random_state is the random
        number generator; If None, the random number generator is the
        RandomState instance used by `np.random`. Used when ``selection`` ==
        'random'.

    selection : str, default 'cyclic'
        If set to 'random', a random coefficient is updated every iteration
        rather than looping over features sequentially by default. This
        (setting to 'random') often leads to significantly faster convergence
        especially when tol is higher than 1e-4.

    Attributes
    ----------
    coef_ : array, shape (n_features,) | (n_targets, n_features)
        parameter vector (w in the cost function formula)

    intercept_ : float | array, shape (n_targets,)
        independent term in decision function.

    n_iter_ : int | array-like, shape (n_targets,)
        number of iterations run by the coordinate descent solver to reach
        the specified tolerance.
    """

    def __init__(self, alpha=1.0, fit_intercept=True, normalize=False,
                 copy_X=True, max_iter=1000, tol=1e-4, warm_start=False,
                 random_state=None, selection='cyclic'):
        super().__init__(
            alpha=alpha, fit_intercept=fit_intercept, normalize=False,
            copy_X=copy_X, max_iter=max_iter, tol=tol, warm_start=warm_start,
            random_state=random_state, selection=selection)

    def fit(self, X, y, sample_weight=None):
        """Fit model with coordinate descent.

        Parameters
        ----------
        X : ndarray or scipy.sparse matrix, (n_samples, n_features)
            Data

        y : ndarray, shape (n_samples,) or (n_samples, n_targets)
            Target. Will be cast to X's dtype if necessary

        sample_weight : numpy array of shape [n_samples]
                        Individual weights for each sample.
                        The weights will be normalized internally.
        """
        _fit_weighted_linear_model(self, WeightedMultiTaskLasso, X, y, sample_weight)
        return self


class WeightedLassoCV(LassoCV):
    """Version of sklearn LassoCV that accepts weights.

    Parameters
    ----------
    eps : float, optional
        Length of the path. ``eps=1e-3`` means that
        ``alpha_min / alpha_max = 1e-3``.

    n_alphas : int, optional
        Number of alphas along the regularization path

    alphas : numpy array, optional
        List of alphas where to compute the models.
        If ``None`` alphas are set automatically

    fit_intercept : boolean, default True
        whether to calculate the intercept for this model. If set
        to false, no intercept will be used in calculations
        (e.g. data is expected to be already centered).

    precompute : True | False | 'auto' | array-like
        Whether to use a precomputed Gram matrix to speed up
        calculations. If set to ``'auto'`` let us decide. The Gram
        matrix can also be passed as argument.

    max_iter : int, optional
        The maximum number of iterations

    tol : float, optional
        The tolerance for the optimization: if the updates are
        smaller than ``tol``, the optimization code checks the
        dual gap for optimality and continues until it is smaller
        than ``tol``.

    copy_X : boolean, optional, default True
        If ``True``, X will be copied; else, it may be overwritten.

    cv : int, cross-validation generator or an iterable, optional
        Determines the cross-validation splitting strategy.
        Possible inputs for cv are:
        - None, to use the default 3-fold weighted cross-validation,
        - integer, to specify the number of folds.
        - :term:`CV splitter`,
        - An iterable yielding (train, test) splits as arrays of indices.
        For integer/None inputs, :class:`WeightedKFold` is used.

    verbose : bool or integer
        Amount of verbosity.

    n_jobs : int or None, optional (default=None)
        Number of CPUs to use during the cross validation.
        ``None`` means 1 unless in a :obj:`joblib.parallel_backend` context.
        ``-1`` means using all processors. See :term:`Glossary <n_jobs>`
        for more details.

    positive : bool, optional
        If positive, restrict regression coefficients to be positive

    random_state : int, RandomState instance or None, optional, default None
        The seed of the pseudo random number generator that selects a random
        feature to update.  If int, random_state is the seed used by the random
        number generator; If RandomState instance, random_state is the random
        number generator; If None, the random number generator is the
        RandomState instance used by `np.random`. Used when ``selection`` ==
        'random'.

    selection : str, default 'cyclic'
        If set to 'random', a random coefficient is updated every iteration
        rather than looping over features sequentially by default. This
        (setting to 'random') often leads to significantly faster convergence
        especially when tol is higher than 1e-4.
    """

    def __init__(self, eps=1e-3, n_alphas=100, alphas=None, fit_intercept=True,
                 precompute='auto', max_iter=1000, tol=1e-4, normalize=False,
                 copy_X=True, cv='warn', verbose=False, n_jobs=None,
                 positive=False, random_state=None, selection='cyclic'):

        super().__init__(
            eps=eps, n_alphas=n_alphas, alphas=alphas,
            fit_intercept=fit_intercept, normalize=False,
            precompute=precompute, max_iter=max_iter, tol=tol, copy_X=copy_X,
            cv=cv, verbose=verbose, n_jobs=n_jobs, positive=positive,
            random_state=random_state, selection=selection)

    def fit(self, X, y, sample_weight=None):
        """Fit model with coordinate descent.

        Parameters
        ----------
        X : ndarray or scipy.sparse matrix, (n_samples, n_features)
            Data

        y : ndarray, shape (n_samples,) or (n_samples, n_targets)
            Target. Will be cast to X's dtype if necessary

        sample_weight : numpy array of shape [n_samples]
                        Individual weights for each sample.
                        The weights will be normalized internally.
        """
        # Make weighted splitter
        cv_temp = self.cv
        self.cv = _weighted_check_cv(self.cv).split(X, y, sample_weight=sample_weight)
        # Fit weighted model
        _fit_weighted_linear_model(self, WeightedLassoCV, X, y, sample_weight)
        self.cv = cv_temp
        return self


class WeightedMultiTaskLassoCV(MultiTaskLassoCV):
    """Version of sklearn MultiTaskLassoCV that accepts weights.

    Parameters
    ----------
    eps : float, optional
        Length of the path. ``eps=1e-3`` means that
        ``alpha_min / alpha_max = 1e-3``.

    n_alphas : int, optional
        Number of alphas along the regularization path

    alphas : array-like, optional
        List of alphas where to compute the models.
        If not provided, set automatically.

    fit_intercept : boolean
        whether to calculate the intercept for this model. If set
        to false, no intercept will be used in calculations
        (e.g. data is expected to be already centered).

    max_iter : int, optional
        The maximum number of iterations.

    tol : float, optional
        The tolerance for the optimization: if the updates are
        smaller than ``tol``, the optimization code checks the
        dual gap for optimality and continues until it is smaller
        than ``tol``.

    copy_X : boolean, optional, default True
        If ``True``, X will be copied; else, it may be overwritten.

    cv : int, cross-validation generator or an iterable, optional
        Determines the cross-validation splitting strategy.
        Possible inputs for cv are:
        - None, to use the default 3-fold weighted cross-validation,
        - integer, to specify the number of folds.
        - :term:`CV splitter`,
        - An iterable yielding (train, test) splits as arrays of indices.
        For integer/None inputs, :class:`WeightedKFold` is used.

    verbose : bool or integer
        Amount of verbosity.

    n_jobs : int or None, optional (default=None)
        Number of CPUs to use during the cross validation. Note that this is
        used only if multiple values for l1_ratio are given.
        ``None`` means 1 unless in a :obj:`joblib.parallel_backend` context.
        ``-1`` means using all processors. See :term:`Glossary <n_jobs>`
        for more details.

    random_state : int, RandomState instance or None, optional, default None
        The seed of the pseudo random number generator that selects a random
        feature to update.  If int, random_state is the seed used by the random
        number generator; If RandomState instance, random_state is the random
        number generator; If None, the random number generator is the
        RandomState instance used by `np.random`. Used when ``selection`` ==
        'random'

    selection : str, default 'cyclic'
        If set to 'random', a random coefficient is updated every iteration
        rather than looping over features sequentially by default. This
        (setting to 'random') often leads to significantly faster convergence
        especially when tol is higher than 1e-4.
    """

    def __init__(self, eps=1e-3, n_alphas=100, alphas=None, fit_intercept=True,
                 normalize=False, max_iter=1000, tol=1e-4,
                 copy_X=True, cv='warn', verbose=False, n_jobs=None,
                 random_state=None, selection='cyclic'):

        super().__init__(
            eps=eps, n_alphas=n_alphas, alphas=alphas,
            fit_intercept=fit_intercept, normalize=False,
            max_iter=max_iter, tol=tol, copy_X=copy_X,
            cv=cv, verbose=verbose, n_jobs=n_jobs,
            random_state=random_state, selection=selection)

    def fit(self, X, y, sample_weight=None):
        """Fit model with coordinate descent.

        Parameters
        ----------
        X : ndarray or scipy.sparse matrix, (n_samples, n_features)
            Data

        y : ndarray, shape (n_samples,) or (n_samples, n_targets)
            Target. Will be cast to X's dtype if necessary

        sample_weight : numpy array of shape [n_samples]
                        Individual weights for each sample.
                        The weights will be normalized internally.
        """
        # Make weighted splitter
        cv_temp = self.cv
        self.cv = _weighted_check_cv(self.cv).split(X, y, sample_weight=sample_weight)
        # Fit weighted model
        _fit_weighted_linear_model(self, WeightedMultiTaskLassoCV, X, y, sample_weight)
        self.cv = cv_temp
        return self


class DebiasedLasso(WeightedLasso):
    """Debiased Lasso model.

    Implementation was derived from <https://arxiv.org/abs/1303.0518>.

    Only implemented for single-dimensional output.

    Parameters
    ----------
    alpha : string | float, optional. Default='auto'.
        Constant that multiplies the L1 term. Defaults to 'auto'.
        ``alpha = 0`` is equivalent to an ordinary least square, solved
        by the :class:`LinearRegression` object. For numerical
        reasons, using ``alpha = 0`` with the ``Lasso`` object is not advised.
        Given this, you should use the :class:`LinearRegression` object.

    fit_intercept : boolean, optional, default True
        Whether to calculate the intercept for this model. If set
        to False, no intercept will be used in calculations
        (e.g. data is expected to be already centered).

    precompute : True | False | array-like, default=False
        Whether to use a precomputed Gram matrix to speed up
        calculations. If set to ``'auto'`` let us decide. The Gram
        matrix can also be passed as argument. For sparse input
        this option is always ``True`` to preserve sparsity.

    copy_X : boolean, optional, default True
        If ``True``, X will be copied; else, it may be overwritten.

    max_iter : int, optional
        The maximum number of iterations

    tol : float, optional
        The tolerance for the optimization: if the updates are
        smaller than ``tol``, the optimization code checks the
        dual gap for optimality and continues until it is smaller
        than ``tol``.

    warm_start : bool, optional
        When set to True, reuse the solution of the previous call to fit as
        initialization, otherwise, just erase the previous solution.
        See :term:`the Glossary <warm_start>`.

    positive : bool, optional
        When set to ``True``, forces the coefficients to be positive.

    random_state : int, RandomState instance or None, optional, default None
        The seed of the pseudo random number generator that selects a random
        feature to update.  If int, random_state is the seed used by the random
        number generator; If RandomState instance, random_state is the random
        number generator; If None, the random number generator is the
        RandomState instance used by `np.random`. Used when ``selection`` ==
        'random'.

    selection : str, default 'cyclic'
        If set to 'random', a random coefficient is updated every iteration
        rather than looping over features sequentially by default. This
        (setting to 'random') often leads to significantly faster convergence
        especially when tol is higher than 1e-4.

    Attributes
    ----------
    coef_ : array, shape (n_features,)
        Parameter vector (w in the cost function formula).

    intercept_ : float
        Independent term in decision function.

    n_iter_ : int | array-like, shape (n_targets,)
        Number of iterations run by the coordinate descent solver to reach
        the specified tolerance.

    selected_alpha_ : float
        Penalty chosen through cross-validation, if alpha='auto'.

    coef_std_err_ : array, shape (n_features,)
        Estimated standard errors for coefficients (see 'coef_' attribute).

    intercept_std_err_ : float
        Estimated standard error intercept (see 'intercept_' attribute).

    """

    def __init__(self, alpha='auto', fit_intercept=True,
                 precompute=False, copy_X=True, max_iter=1000,
                 tol=1e-4, warm_start=False, positive=False,
                 random_state=None, selection='cyclic'):
        super().__init__(
            alpha=alpha, fit_intercept=fit_intercept,
            precompute=precompute, copy_X=copy_X,
            max_iter=max_iter, tol=tol, warm_start=warm_start,
            positive=positive, random_state=random_state,
            selection=selection)

    def fit(self, X, y, sample_weight=None, check_input=True):
        """Fit debiased lasso model.

        Parameters
        ----------
        X : ndarray or scipy.sparse matrix, (n_samples, n_features)
            Input data.

        y : array, shape (n_samples,)
            Target. Will be cast to X's dtype if necessary

        sample_weight : numpy array of shape [n_samples]
                        Individual weights for each sample.
                        The weights will be normalized internally.

        check_input : boolean, (default=True)
            Allow to bypass several input checking.
            Don't use this parameter unless you know what you do.
        """
        alpha_grid = [0.01, 0.02, 0.03, 0.06, 0.1, 0.2, 0.3, 0.5, 0.8, 1]
        self.selected_alpha_ = None
        if self.alpha == 'auto':
            # Select optimal penalty
            self.alpha = self._get_optimal_alpha(
                alpha_grid, X, y, sample_weight)
            self.selected_alpha_ = self.alpha
        else:
            # Warn about consistency
            warnings.warn("Setting a suboptimal alpha can lead to miscalibrated confidence intervals. "
                          "We recommend setting alpha='auto' for optimality.")

        # Convert X, y into numpy arrays
        X, y = check_X_y(X, y, y_numeric=True, multi_output=False)
        # Fit weighted lasso with user input
        super().fit(X, y, sample_weight, check_input)
        # Center X, y
        X, y, X_offset, y_offset, X_scale = self._preprocess_data(
            X, y, fit_intercept=self.fit_intercept, normalize=False,
            copy=self.copy_X, check_input=check_input, sample_weight=sample_weight, return_mean=True)

        # Calculate quantities that will be used later on. Account for centered data
        y_pred = self.predict(X) - self.intercept_
        self._theta_hat = self._get_theta_hat(X, sample_weight)
        self._X_offset = X_offset

        # Calculate coefficient and error variance
        num_nonzero_coefs = np.count_nonzero(self.coef_)
        self._error_variance = np.average((y - y_pred)**2, weights=sample_weight) / \
            (1 - num_nonzero_coefs / X.shape[0])
        self._mean_error_variance = self._error_variance / X.shape[0]
        self._coef_variance = self._get_unscaled_coef_var(
            X, self._theta_hat, sample_weight) * self._error_variance

        # Add coefficient correction
        coef_correction = self._get_coef_correction(
            X, y, y_pred, sample_weight, self._theta_hat)
        self.coef_ += coef_correction

        # Set coefficients and intercept standard errors
        self.coef_std_err_ = np.sqrt(np.diag(self._coef_variance))
        if self.fit_intercept:
            self.intercept_std_err_ = np.sqrt(
                self._X_offset @ self._coef_variance @ self._X_offset +
                self._mean_error_variance
            )
        else:
            self.intercept_std_err_ = 0

        # Set intercept
        self._set_intercept(X_offset, y_offset, X_scale)
        # Return alpha to 'auto' state
        if self.selected_alpha_ is not None:
            self.alpha = 'auto'
        return self

    def predict_interval(self, X, lower=5, upper=95):
        """Build prediction confidence intervals using the debiased lasso.

        Parameters
        ----------
        X : ndarray or scipy.sparse matrix, (n_samples, n_features)
            Samples.

        lower : float, optional
            Lower percentile. Must be a number between 0 and 100.
            Defaults to 5.0.

        upper : float, optional
            Upper percentile. Must be a number between 0 and 100, larger than 'lower'.
            Defaults to 95.0.

        Returns
        -------
        (y_lower, y_upper) : tuple of arrays, shape (n_samples, )
            Returns lower and upper interval endpoints.
        """
        y_pred = self.predict(X)
        y_lower = np.empty(y_pred.shape)
        y_upper = np.empty(y_pred.shape)
        # Note that in the case of no intercept, X_offset is 0
        if self.fit_intercept:
            X = X - self._X_offset
        # Calculate the variance of the predictions
        var_pred = np.sum(np.matmul(X, self._coef_variance) * X, axis=1)
        if self.fit_intercept:
            var_pred += self._mean_error_variance

        # Calculate prediction confidence intervals
        sd_pred = np.sqrt(var_pred)
        y_lower = y_pred + \
            np.apply_along_axis(lambda s: norm.ppf(
                lower / 100, scale=s), 0, sd_pred)
        y_upper = y_pred + \
            np.apply_along_axis(lambda s: norm.ppf(
                upper / 100, scale=s), 0, sd_pred)
        return y_lower, y_upper

    def _get_coef_correction(self, X, y, y_pred, sample_weight, theta_hat):
        # Assumes flattened y
        n_samples, n_features = X.shape
        y_res = np.ndarray.flatten(y) - y_pred
        # Compute weighted residuals
        if sample_weight is not None:
            y_res_scaled = y_res * sample_weight / np.sum(sample_weight)
        else:
            y_res_scaled = y_res / n_samples
        delta_coef = np.matmul(
            np.matmul(theta_hat, X.T), y_res_scaled)
        return delta_coef

    def _get_optimal_alpha(self, alpha_grid, X, y, sample_weight):
        # To be done once per target. Assumes y can be flattened.
        cv_estimator = WeightedLassoCV(alphas=alpha_grid, cv=5, fit_intercept=self.fit_intercept)
        cv_estimator.fit(X, y.flatten(), sample_weight=sample_weight)
        return cv_estimator.alpha_

    def _get_theta_hat(self, X, sample_weight):
        # Assumes that X has already been offset
        n_samples, n_features = X.shape
        coefs = np.empty((n_features, n_features - 1))
        tausq = np.empty(n_features)
        # Compute Lasso coefficients for the columns of the design matrix
        for i in range(n_features):
            y = X[:, i]
            X_reduced = X[:, list(range(i)) + list(range(i + 1, n_features))]
            # Call weighted lasso on reduced design matrix
            # Inherit some parameters from the parent
            local_wlasso = WeightedLasso(
                alpha=self.alpha,
                fit_intercept=False,
                max_iter=self.max_iter,
                tol=self.tol
            ).fit(X_reduced, y, sample_weight=sample_weight)
            coefs[i] = local_wlasso.coef_
            # Weighted tau
            if sample_weight is not None:
                y_weighted = y * sample_weight / np.sum(sample_weight)
            else:
                y_weighted = y / n_samples
            tausq[i] = np.dot(y - local_wlasso.predict(X_reduced), y_weighted)
        # Compute C_hat
        C_hat = np.diag(np.ones(n_features))
        C_hat[0][1:] = -coefs[0]
        for i in range(1, n_features):
            C_hat[i][:i] = -coefs[i][:i]
            C_hat[i][i + 1:] = -coefs[i][i:]
        # Compute theta_hat
        theta_hat = np.matmul(np.diag(1 / tausq), C_hat)
        return theta_hat

    def _get_unscaled_coef_var(self, X, theta_hat, sample_weight):
        if sample_weight is not None:
            weights_mat = np.diag(sample_weight / np.sum(sample_weight))
            sigma = X.T @ weights_mat @ X
        else:
            sigma = np.matmul(X.T, X) / X.shape[0]
        _unscaled_coef_var = np.matmul(
            np.matmul(theta_hat, sigma), theta_hat.T) / X.shape[0]
        return _unscaled_coef_var


class MultiOutputDebiasedLasso(MultiOutputRegressor):
    """Debiased Multi Output Lasso model.

    Implementation was derived from <https://arxiv.org/abs/1303.0518>.

    Parameters
    ----------
    alpha : string | float, optional. Default='auto'.
        Constant that multiplies the L1 term. Defaults to 'auto'.
        ``alpha = 0`` is equivalent to an ordinary least square, solved
        by the :class:`LinearRegression` object. For numerical
        reasons, using ``alpha = 0`` with the ``Lasso`` object is not advised.
        Given this, you should use the :class:`LinearRegression` object.

    fit_intercept : boolean, optional, default True
        Whether to calculate the intercept for this model. If set
        to False, no intercept will be used in calculations
        (e.g. data is expected to be already centered).

    precompute : True | False | array-like, default=False
        Whether to use a precomputed Gram matrix to speed up
        calculations. If set to ``'auto'`` let us decide. The Gram
        matrix can also be passed as argument. For sparse input
        this option is always ``True`` to preserve sparsity.

    copy_X : boolean, optional, default True
        If ``True``, X will be copied; else, it may be overwritten.

    max_iter : int, optional
        The maximum number of iterations

    tol : float, optional
        The tolerance for the optimization: if the updates are
        smaller than ``tol``, the optimization code checks the
        dual gap for optimality and continues until it is smaller
        than ``tol``.

    warm_start : bool, optional
        When set to True, reuse the solution of the previous call to fit as
        initialization, otherwise, just erase the previous solution.
        See :term:`the Glossary <warm_start>`.

    positive : bool, optional
        When set to ``True``, forces the coefficients to be positive.

    random_state : int, RandomState instance or None, optional, default None
        The seed of the pseudo random number generator that selects a random
        feature to update.  If int, random_state is the seed used by the random
        number generator; If RandomState instance, random_state is the random
        number generator; If None, the random number generator is the
        RandomState instance used by `np.random`. Used when ``selection`` ==
        'random'.

    selection : str, default 'cyclic'
        If set to 'random', a random coefficient is updated every iteration
        rather than looping over features sequentially by default. This
        (setting to 'random') often leads to significantly faster convergence
        especially when tol is higher than 1e-4.

    Attributes
    ----------
    coef_ : array, shape (n_targets, n_features)
        Parameter vector (w in the cost function formula).

    intercept_ : (n_targets, )
        Independent term in decision function.

    selected_alpha_ : float or (n_targets_)
        Penalty chosen through cross-validation, if alpha='auto'.

    coef_std_err_ : array, shape (n_targets, n_features)
        Estimated standard errors for coefficients (see 'coef_' attribute).

    intercept_std_err_ : (n_targets, )
        Estimated standard error intercept (see 'intercept_' attribute).

    """

    def __init__(self, alpha='auto', fit_intercept=True,
                 precompute=False, copy_X=True, max_iter=1000,
                 tol=1e-4, warm_start=False, positive=False,
                 random_state=None, selection='cyclic', n_jobs=None):
        estimator = DebiasedLasso(alpha=alpha, fit_intercept=fit_intercept,
                                  precompute=precompute, copy_X=copy_X, max_iter=max_iter,
                                  tol=tol, warm_start=warm_start, positive=False,
                                  random_state=None, selection='cyclic')
        super().__init__(estimator=estimator, n_jobs=n_jobs)

    def fit(self, X, y, sample_weight=None):
        """Fit the multi-output debiased lasso model.

        Parameters
        ----------
        X : ndarray or scipy.sparse matrix, (n_samples, n_features)
            Input data.

        y : array, shape (n_samples, n_targets)
            Target. Will be cast to X's dtype if necessary

        sample_weight : numpy array of shape [n_samples]
                        Individual weights for each sample.
                        The weights will be normalized internally.
        """
        super().fit(X, y, sample_weight)
        # Set coef_ attribute
        self._set_attribute("coef_")
        # Set intercept_ attribute
        self._set_attribute("intercept_",
                            condition=self.estimators_[0].fit_intercept,
                            default=0.0)
        # Set selected_alpha_ attribute
        self._set_attribute("intercept_",
                            condition=(self.estimators_[0].alpha == 'auto'))
        # Set coef_std_err_
        self._set_attribute("coef_std_err_")
        # intercept_std_err_
        self._set_attribute("intercept_std_err_")

    def predict_interval(self, X, lower=5, upper=95):
        """Build prediction confidence intervals using the debiased lasso.

        Parameters
        ----------
        X : ndarray or scipy.sparse matrix, (n_samples, n_features)
            Samples.

        lower : float, optional
            Lower percentile. Must be a number between 0 and 100.
            Defaults to 5.0.

        upper : float, optional
            Upper percentile. Must be a number between 0 and 100, larger than 'lower'.
            Defaults to 95.0.

        Returns
        -------
        (y_lower, y_upper) : tuple of arrays, shape (n_samples, n_targets)
            Returns lower and upper interval endpoints.
        """
        n_estimators = len(self.estimators_)
        X = check_array(X)
        y_lower = np.empty((X.shape[0], n_estimators))
        y_upper = np.empty((X.shape[0], n_estimators))
        for i, estimator in enumerate(self.estimators_):
            y_lower[:, i], y_upper[:, i] = estimator.predict_interval(X, lower=lower, upper=upper)
        return y_lower, y_upper

    def get_params(self, deep=True):
        """Get parameters for this estimator."""
        param_mapping = super().get_params(deep=deep)
        new_param_mapping = {self._transform_param(k): v for (k, v) in param_mapping.items()}
        return new_param_mapping

    def set_params(self, **params):
        """Set parameters for this estimator."""
        new_params = {self._inverse_transform_param(k): v for (k, v) in params.items()}
        return super().set_params(**new_params)

    def _transform_param(self, param):
        transformed_param = param.split("estimator__")[1] if "estimator__" in param else param
        return transformed_param

    def _inverse_transform_param(self, param):
        param_mapping = super().get_params()
        inverse_transformed_param = f"estimator__{param}"
        if inverse_transformed_param in param_mapping:
            return inverse_transformed_param
        return param

    def _set_attribute(self, attribute_name, condition=True, default=None):
        if condition:
            attribute_value = np.array([getattr(estimator, attribute_name) for estimator in self.estimators_])
        else:
            attribute_value = default
        setattr(self, attribute_name, attribute_value)