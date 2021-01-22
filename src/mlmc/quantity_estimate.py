import numpy as np
import mlmc.quantity
import mlmc.quantity_types as qt
from mlmc.quantity_spec import ChunkSpec


def mask_nan_samples(chunk):
    """
    Mask out samples that contain NaN in either fine or coarse part of the result
    :param chunk: np.ndarray [M, chunk_size, 2]
    :return: chunk: np.ndarray, number of masked samples: int
    """
    # Fine and coarse moments_fn mask
    mask = np.any(np.isnan(chunk), axis=0).any(axis=1)
    return chunk[..., ~mask, :], np.count_nonzero(mask)


def cache_clear():
    mlmc.quantity.Quantity.samples.cache_clear()
    mlmc.quantity.QuantityConst.samples.cache_clear()


def estimate_mean(quantity, chunk_size=512000000):
    """
    MLMC mean estimator.
    The MLMC method is used to compute the mean estimate to the Quantity dependent on the collected samples.
    The squared error of the estimate (the estimator variance) is estimated using the central limit theorem.
    Data is processed by chunks, so that it also supports big data processing
    :param quantity: Quantity
    :param chunk_size: chunk size in bytes in decimal, determines number of samples in chunk
    :return: QuantityMean which holds both mean and variance
    """
    #cache_clear()
    quantity_vec_size = quantity.size()
    sums = None
    sums_of_squares = None
    #chunk_id = 0
    #level_chunks_none = np.zeros(1)  # if ones then the iteration through the chunks was terminated at each level

    # initialization
    level_ids = quantity.get_quantity_storage().level_ids()
    n_levels = len(level_ids)
    n_samples = [0] * n_levels
    n_rm_samples = [0] * n_levels

    for level_id in level_ids:
        try:
            chunk_id = 0
            # TODO: we should pass chunk_id to quantity.samples due to the use of CACHE
            # TODO: Generators work well from direct storage access, but how to use it in for loop through input_quantites (see Quantity.sample)?
            for chunk_spec in quantity.samples(level_id, chunk_size=chunk_size):
                print("level_id: {}, chunk_id: {}".format(level_id, chunk_id))

                # print("chunk_spec ", chunk_spec)
                # print("type(chunk_spec) ", type(chunk_spec))
                # print("chunk_spec.data.shape ", chunk_spec.data.shape)
                #
                # print("quantity.qtype.size() ", quantity.qtype.size())
                # print("chunk_spec.data.shape[0] ", chunk_spec.data.shape[0])
                # print("chunk_spec.data.shape", chunk_spec.data.shape)
                # print("chunk_spec.data", chunk_spec.data)
                # print("type(chunk_spec.data)", type(chunk_spec.data))

                chunk, n_mask_samples = mask_nan_samples(chunk_spec.data)
                # level_chunk is Numpy Array with shape [M, chunk_size, 2]
                n_samples[level_id] += chunk.shape[1]
                n_rm_samples[level_id] += n_mask_samples

                # No samples in chunk
                if chunk.shape[1] == 0:
                    continue
                assert (chunk.shape[0] == quantity_vec_size)

                # Set variables for level sums and sums of squares
                if sums is None:
                    sums = [np.zeros(chunk.shape[0]) for _ in range(n_levels)]
                    sums_of_squares = [np.zeros(chunk.shape[0]) for _ in range(n_levels)]

                if level_id == 0:
                    chunk_diff = chunk[:, :, 0]
                else:
                    chunk_diff = chunk[:, :, 0] - chunk[:, :, 1]

                sums[level_id] += np.sum(chunk_diff, axis=1)
                sums_of_squares[level_id] += np.sum(chunk_diff**2, axis=1)

                chunk_id += 1
        except StopIteration:
            pass

    if sums is None:
        raise Exception("All samples were masked")

    l_means = []
    l_vars = []
    for s, sp, n in zip(sums, sums_of_squares, n_samples):
        l_means.append(s / n)
        if n > 1:
            l_vars.append((sp - (s ** 2 / n)) / (n-1))
        else:
            l_vars.append(np.full(len(s), np.inf))

    return mlmc.quantity.QuantityMean(quantity.qtype, l_means=l_means, l_vars=l_vars, n_samples=n_samples,
                                      n_rm_samples=n_rm_samples)


def moment(quantity, moments_fn, i=0):
    """
    Create quantity with operation that evaluates particular moment
    :param quantity: Quantity instance
    :param moments_fn: mlmc.moments.Moments child
    :param i: index of moment
    :return: Quantity
    """
    def eval_moment(x):
        return moments_fn.eval_single_moment(i, value=x)
    return mlmc.quantity.Quantity(quantity_type=quantity.qtype, input_quantities=[quantity], operation=eval_moment)


def moments(quantity, moments_fn, mom_at_bottom=True):
    """
    Create quantity with operation that evaluates moments_fn
    :param quantity: Quantity
    :param moments_fn: mlmc.moments.Moments child
    :param mom_at_bottom: bool, if True moments_fn are underneath
    :return: Quantity
    """
    def eval_moments(x):
        if mom_at_bottom:
            mom = moments_fn.eval_all(x).transpose((0, 3, 1, 2))  # [M, R, N, 2]
        else:
            mom = moments_fn.eval_all(x).transpose((3, 0, 1, 2))  # [R, M, N, 2]
        return mom.reshape((np.prod(mom.shape[:-2]), mom.shape[-2], mom.shape[-1]))  # [M, N, 2]

    # Create quantity type which has moments_fn at the bottom
    if mom_at_bottom:
        moments_array_type = qt.ArrayType(shape=(moments_fn.size,), qtype=qt.ScalarType())
        moments_qtype = quantity.qtype.replace_scalar(moments_array_type)
    # Create quantity type that has moments_fn on the surface
    else:
        moments_qtype = qt.ArrayType(shape=(moments_fn.size,), qtype=quantity.qtype)
    return mlmc.quantity.Quantity(quantity_type=moments_qtype, input_quantities=[quantity], operation=eval_moments)


def covariance(quantity, moments_fn, cov_at_bottom=True):
    """
    Create quantity with operation that evaluates covariance matrix
    :param quantity: Quantity
    :param moments_fn: mlmc.moments.Moments child
    :param cov_at_bottom: bool, if True cov matrices are underneath
    :return: Quantity
    """
    def eval_cov(x):
        moments = moments_fn.eval_all(x)
        mom_fine = moments[..., 0, :]
        cov_fine = np.einsum('...i,...j', mom_fine, mom_fine)

        if moments.shape[-2] == 1:
            cov = np.array([cov_fine])
        else:
            mom_coarse = moments[..., 1, :]
            cov_coarse = np.einsum('...i,...j', mom_coarse, mom_coarse)
            cov = np.array([cov_fine, cov_coarse])

        if cov_at_bottom:
            cov = cov.transpose((1, 3, 4, 2, 0))   # [M, R, R, N, 2]
        else:
            cov = cov.transpose((3, 4, 1, 2, 0))   # [R, R, M, N, 2]
        return cov.reshape((np.prod(cov.shape[:-2]), cov.shape[-2], cov.shape[-1]))

    # Create quantity type which has covariance matrices at the bottom
    if cov_at_bottom:
        moments_array_type = qt.ArrayType(shape=(moments_fn.size, moments_fn.size, ), qtype=qt.ScalarType())
        moments_qtype = quantity.qtype.replace_scalar(moments_array_type)
    # Create quantity type that has covariance matrices on the surface
    else:
        moments_qtype = qt.ArrayType(shape=(moments_fn.size, moments_fn.size, ), qtype=quantity.qtype)
    return mlmc.quantity.Quantity(quantity_type=moments_qtype, input_quantities=[quantity], operation=eval_cov)
