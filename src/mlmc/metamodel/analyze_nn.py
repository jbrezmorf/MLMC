import os
import numpy as np
import time
import glob
import copy
import pickle

os.environ["CUDA_VISIBLE_DEVICES"] = "-1"  # Run on CPU only
from mlmc.metamodel.flow_dataset import FlowDataset
from mlmc.metamodel.create_graph import graph_creator
from mlmc.moments import Legendre_tf, Monomial
from mlmc.metamodel.random_field_time import corr_field_sample_time
from mlmc.tool import plot
import matplotlib.pyplot as plt
# Make numpy printouts easier to read.

# np.set_printoptions(precision=9, suppress=True)
import tensorflow as tf
from tensorflow import keras
from scipy.stats import ks_2samp
import sklearn.model_selection
from mlmc.metamodel.custom_methods import abs_activation, MSE_moments
from mlmc.metamodel.postprocessing import analyze_results, plot_loss, estimate_density, process_mlmc
from mlmc.metamodel.flow_task_NN import DNN
from mlmc.metamodel.flow_task_CNN import CNN

from mlmc.metamodel.flow_task_GNN_2 import GNN
from tensorflow.keras.losses import MeanSquaredError
from spektral.data import MixedLoader
from spektral.layers.ops import sp_matrix_to_sp_tensor

print("Num GPUs Available: ", len(tf.config.experimental.list_physical_devices('GPU')))
epochs = 100

def prepare_data(data):
    data = np.squeeze(np.stack(data.to_numpy(), axis=0))
    return np.asarray(data).astype('float64')


def split_dataset(dataset):
    # Load data
    dataset = dataset.dropna()
    train_x, test_x, train_y, test_y = sklearn.model_selection.train_test_split(dataset.x, dataset.y,
                                                                                test_size=0.2, random_state=123)

    train_x = prepare_data(train_x)
    train_y = prepare_data(train_y)

    test_x = prepare_data(test_x)
    test_y = prepare_data(test_y)

    return train_x, train_y, test_x, test_y


def run():
    # Parameters
    loss = "mean_squared_error"
    optimizer = tf.optimizers.Adam(learning_rate=0.001)

    data = FlowDataset()
    # dataset = data.dataset[:10000]
    # test_dataset = data.dataset[10000:50000]

    dataset = data.dataset[:50000]
    test_dataset = data.dataset[50000:]

    train_input = prepare_data(dataset.x)
    train_output = prepare_data(dataset.y)

    # train_input, train_output, test__input, test_output = split_dataset(dataset)
    # print("len test(output) ", len(test_output))

    dnn = DNN(loss=loss, optimizer=optimizer, output_activation=abs_activation, hidden_activation='relu', epochs=150)
    dnn.fit(train_input, train_output)

    test_input = prepare_data(test_dataset.x)
    test_output = prepare_data(test_dataset.y)

    predictions = dnn.predict(test_input)
    predictions = np.squeeze(predictions)

    print("len(predictions) ", len(predictions))

    plot_loss(dnn.history.history['loss'], dnn.history.history['val_loss'])
    analyze_results(test_output, predictions)

    estimate_density(test_output)
    estimate_density(predictions)


def run_CNN(output_dir, hdf_path, l_0_output_dir, l_0_hdf_path, save_path, mesh, level, log):
    # Parameters
    loss = "mean_squared_error"
    optimizer = tf.optimizers.Adam(learning_rate=0.01)

    data = FlowDataset(output_dir=output_dir, level=level, log=log)
    dataset = data.dataset[:]

    train_input, train_output, test_input, test_output = split_dataset(dataset)

    train_input = train_input[:2000]
    train_output = train_output[:2000]

    print("len test(output) ", len(test_output))

    train_input = np.expand_dims(train_input, axis=-1)
    test_input = np.expand_dims(test_input, axis=-1)
    print("train input shape ", train_input.shape)

    dnn = CNN(loss=loss, optimizer=optimizer, output_activation=abs_activation, hidden_activation='relu')

    dnn.fit(train_input, train_output)

    test_dataset = data.dataset[2000:]
    test_input = prepare_data(test_dataset.x)
    test_input = np.expand_dims(test_input, axis=-1)
    print("test input shape ", test_input.shape)
    test_output = prepare_data(test_dataset.y)

    predictions = dnn.predict(test_input)
    predictions = np.squeeze(predictions)

    plot_loss(dnn.history.history['loss'], dnn.history.history['val_loss'])

    analyze_results(test_output, predictions)

    # estimate_density(test_output)
    # estimate_density(predictions)


def bootstrap():
    loss = "mean_absolute_error"
    optimizer = tf.optimizers.Adam(learning_rate=0.001)
    n_subsamples = 10
    size = 10000

    train_losses = []
    val_losses = []
    all_test_outputs = []
    all_predictions = []
    ks_statistics = []
    ks_p_values = []

    data = FlowDataset()
    dataset = data.dataset.dropna()

    for i in range(n_subsamples):
        dset = dataset.sample(size, replace=True)
        train_input, train_output, test_input, test_output = split_dataset(dset)

        print("Size TRAIN in: {}, out: {}, TEST in: {}, out: {}".format(len(train_input), len(train_output),
                                                                        len(test_input), len(test_output)))

        dnn = DNN(loss=loss, optimizer=optimizer, output_activation=abs_activation, hidden_activation='relu')
        dnn.fit(train_input, train_output)

        predictions = dnn.predict(test_input)
        predictions = np.squeeze(predictions)

        train_losses.append(dnn.history.history['loss'])
        val_losses.append(dnn.history.history['val_loss'])

        all_test_outputs.append(test_output)
        all_predictions.append(predictions)

        statistics, pvalue = ks_2samp(test_output, predictions)
        ks_statistics.append(statistics)
        ks_p_values.append(pvalue)

    analyze_results(np.mean(all_test_outputs, axis=0), np.mean(all_predictions, axis=0))
    analyze_results(np.var(all_test_outputs, axis=0), np.var(all_predictions, axis=0))
    #
    # estimate_density(np.mean(all_test_outputs, axis=0), title="Test outputs")
    # estimate_density(np.mean(all_predictions, axis=0), title="Predictions")


def run_SVR(config, stats=True, train=True, log=False):
    from sklearn.svm import SVR

    batch_size = 200
    epochs = 1000
    hidden_regularization = None  # l2(2e-10)
    graph_creation_time = config['graph_creation_time']
    if graph_creation_time == 0:
        graph_creator_preproces_time = time.process_time()
        graph_creator(config['output_dir'], config['hdf_path'], config['mesh'], level=config['level'])
        graph_creation_time = time.process_time() - graph_creator_preproces_time
        print("graph creation time ", graph_creation_time)
        exit()

    preprocess_start_time = time.process_time()
    # Load data
    data = FlowDataset(output_dir=config['output_dir'], level=config['level'], log=log)
    data.shuffle()

    dataset = data.dataset
    dataset = dataset.sample(frac=1)

    train = dataset[:config['n_train_samples']]
    test = dataset[config['n_train_samples']:]

    train_input, train_output = train.x, train.y
    test_input, test_output = test.x, test.y

    train_input = prepare_data(train_input)
    train_output = prepare_data(train_output)

    test_input = prepare_data(test_input)
    test_output = prepare_data(test_output)

    # sc_X = StandardScaler()
    # sc_y = StandardScaler()
    # train_input = sc_X.fit_transform(train_input)
    # train_output = sc_y.fit_transform(train_output.reshape(-1,1))
    # test_input = sc_X.fit_transform(test_input)
    # test_output = sc_y.fit_transform(test_output.reshape(-1,1))
    #train_input, train_output, test_input, test_output = split_dataset(dataset)

    preprocess_time = time.process_time() - preprocess_start_time
    preprocess_time = preprocess_time + graph_creation_time
    learning_time_start = time.process_time()

    print("train input ", train_input.shape)
    print("train output ", train_output.shape)

    svr_rbf = SVR(kernel='rbf', verbose=True)  # 'linear' kernel fitting is never-ending and 'poly' kernel gives very bad score (e.g. -2450), sigmoid gives also bad score (e.g. -125)
    svr_rbf.fit(train_input, train_output)
    train_error = svr_rbf.score(train_input, train_output)

    #print("svr_rbf.get_params() ", svr_rbf.get_params())
    total_steps = 0

    #test_input = sc_X.fit_transform(test_input)
    test_error = svr_rbf.score(test_input, test_output)

    targets = test_output
    train_targets = train_output

    # test_y = sc_y.fit_transform(test.y.to_numpy().reshape(-1,1))

    predictions = svr_rbf.predict(test_input)

    print("train error ", train_error)
    print("test error ", test_error)

    train_predictions = svr_rbf.predict(train_input)
    #train_predictions = np.squeeze(train_predictions)

    learning_time = time.process_time() - learning_time_start
    print("learning time ", learning_time)

    val_targets = []

    orig_targets = targets
    orig_predictions = predictions
    print("MSE ", np.mean((predictions - targets) ** 2))

    if log:
        targets = np.exp(targets)
        predictions = np.exp(predictions)

    print("np.var(target-predictions) ", np.var(targets - predictions))

    if not stats:
        #plot_loss(gnn._train_loss, gnn._val_loss)
        analyze_results(targets, predictions)

        import matplotlib.pyplot as plt

        # plt.hist(train_output, bins=50, alpha=0.5, label='train target', density=True)
        # plt.hist(train_predictions, bins=50, alpha=0.5, label='train predictions', density=True)
        #
        # # plt.hist(targets - predictions, bins=50, alpha=0.5, label='predictions', density=True)
        # plt.legend(loc='upper right')
        # # plt.xlim(-0.5, 1000)
        # plt.yscale('log')
        # plt.show()

        plt.hist(targets, bins=50, alpha=0.5, label='target', density=True)
        plt.hist(predictions, bins=50, alpha=0.5, label='predictions', density=True)

        # plt.hist(targets - predictions, bins=50, alpha=0.5, label='predictions', density=True)
        plt.legend(loc='upper right')
        # plt.xlim(-0.5, 1000)
        plt.yscale('log')
        plt.show()

    #predict_l_0_start_time = time.process_time()
    l_0_targets, l_0_predictions, predict_l_0_time = predict_level_zero_SVR(svr_rbf, config['l_0_output_dir'],
                                                                            config['l_0_hdf_path'],
                                                                            config['mesh'], batch_size, log,
                                                                            stats=stats,
                                                                            corr_field_config=config['corr_field_config'])

    val_predictions = []

    if stats:
        l1_sample_time = preprocess_time / len(data) + learning_time / len(data)
        l0_sample_time = predict_l_0_time / len(l_0_targets)

        # print("targets ", targets)
        # print("predictions ", predictions)

        # orig_max_vars, predict_max_vars = process_mlmc(hdf_path, sampling_info_path, ref_mlmc_file, targets, predictions, train_targets,
        #              train_predictions,
        #              val_targets, l_0_targets,
        #              l_0_predictions, l1_sample_time, l0_sample_time, nn_level=level, replace_level=replace_level,
        #                                                stats=stats)

        return svr_rbf, targets, predictions, learning_time, train_targets, train_predictions, \
               val_targets, val_predictions, l_0_targets, l_0_predictions, l1_sample_time, l0_sample_time, total_steps

    save_times(config['save_path'], False, (preprocess_time, len(data)), learning_time, (predict_l_0_time, len(l_0_targets)))
    save_load_data(config['save_path'], False, targets, predictions, train_targets, train_predictions, val_targets, l_0_targets,
                   l_0_predictions)


def predict_level_zero_SVR(nn, output_dir, hdf_path, mesh, batch_size=1000, log=False, stats=False, corr_field_config=None):
    #graph_creator(output_dir, hdf_path, mesh, level=0)
    sample_time = 0
    if corr_field_config:
        sample_time = corr_field_sample_time(mesh, corr_field_config)

    # Load data
    data = FlowDataset(output_dir=output_dir, log=log)
    dataset = data.dataset[:]

    predict_time_start = time.process_time()
    test_input = prepare_data(dataset.x)
    targets = prepare_data(dataset.y)
    #print("data prepared")

    predictions = []
    for i in range(0, len(test_input), batch_size):
        predictions.extend(nn.predict(test_input[i:i + batch_size]))
    predictions = np.array(predictions)
    #print("predictison shape ", predictions.shape)
    predictions = np.squeeze(predictions)

    if log:
        targets = np.exp(targets)
        predictions = np.exp(predictions)
    # analyze_results(targets, predictions)
    predict_time = time.process_time() - predict_time_start
    return targets, predictions, predict_time + sample_time * len(data)


def statistics(config):
    n_subsamples = 2

    model_title, mch_l_model, log = config['machine_learning_model']
    model_data = {}
    model_data["log"] = log

    if not os.path.isdir(config['save_path']):
        os.makedirs(config['save_path'])
    else:
        print("dir exists {}".format(config['save_path']))
        exit()

    for i in range(n_subsamples):
        print("####################################### iter: {}".format(i))
        iter_dir = os.path.join(config['save_path'], "{}".format(i))
        if not os.path.isdir(iter_dir):
            os.makedirs(iter_dir)

            model, targets, predictions, learning_time, train_targets, train_predictions, \
            val_targets, val_predictions, l_0_targets, l_0_predictions, l1_sample_time, l0_sample_time, total_steps, current_patience = \
                mch_l_model(config, stats=True, train=True, log=log)

            if config['save_model']:
                model_data["model"] = model
            model_data["test_targets"] = targets
            model_data["test_predictions"] = predictions
            model_data["train_targets"] = train_targets
            model_data["train_predictions"] = train_predictions
            model_data["val_targets"] = val_targets
            model_data["val_predictions"] = val_predictions
            model_data["l_0_targets"] = l_0_targets
            model_data["l_0_predictions"] = l_0_predictions
            model_data["l1_sample_time"] = l1_sample_time
            model_data["l0_sample_time"] = l0_sample_time
            model_data["total_steps"] = total_steps
            model_data["learning_times"] = learning_time
            model_data["current_patience"] = current_patience
            save_statistics(iter_dir, model_data)

            # save_times(save_path, False, (preprocess_time, len(data)), learning_time, (predict_l_0_time, len(l_0_targets)))
            # save_load_data(save_path, False, targets, predictions, train_targets, val_targets, l_0_targets, l_0_predictions)

    # for i in range(len(train_losses)):
    #     print("train loss ", train_losses[i])
    #     print("test loss ", test_losses[i])
    #     analyze_results(all_targets[i], all_predictions[i])
    #     print("learning time ", learning_times[i])
    #     print("##################################################")


    analyze_statistics(config)

    # plot_loss(train_losses, val_losses)
    # analyze_results(np.mean(all_test_outputs, axis=0), np.mean(all_predictions, axis=0))
    # analyze_results(np.var(all_test_outputs, axis=0), np.var(all_predictions, axis=0))
    #
    # estimate_density(np.mean(all_test_outputs, axis=0), title="Test outputs")
    # estimate_density(np.mean(all_predictions, axis=0), title="Predictions")


def save_statistics(save_dir_path, model_data):
    for file_name, data in model_data.items():
        if file_name == "model" and data is not None:
            data.save(os.path.join(save_dir_path, file_name))
        else:
            np.save(os.path.join(save_dir_path, file_name), data)


def load_statistics(dir_path):
    models_data = {}
    models_data["model"] = []
    models_data["test_targets"] = []
    models_data["test_predictions"] = []
    models_data["train_targets"] = []
    models_data["train_predictions"] = []
    models_data["val_targets"] = []
    models_data["val_predictions"] = []
    models_data["l_0_targets"] = []
    models_data["l_0_predictions"] = []
    models_data["l1_sample_time"] = []
    models_data["l0_sample_time"] = []
    models_data["total_steps"] = []
    models_data["learning_times"] = []
    models_data["current_patience"] = []
    models_data["log"] = []

    #dirs = (os.path.split(dir_path)[-1]).split("_")
    n_iters = 25
    for i in range(n_iters):
        data_dir_path = os.path.join(dir_path, str(i))
        if not os.path.isdir(data_dir_path):
            print("data dir not exists {}".format(data_dir_path))
            break
        if os.path.exists(os.path.join(data_dir_path,'model')):
            models_data['model'].append(keras.models.load_model(os.path.join(data_dir_path, 'model')))
        for file in glob.glob(os.path.join(data_dir_path, "*.npy")):
            file_name = os.path.split(file)[-1]
            file_name = file_name.split(".")[0]
            models_data[file_name].append(np.load(file))

    return models_data


def plot_sse(data_nn, data_mlmc, x_label="ith moment", y_label="MSE", title=""):
    import matplotlib
    #matplotlib.rcParams.update({'font.size': 38})
    matplotlib.rcParams.update({'lines.markersize': 14})
    fig, axes = plt.subplots(1, 1, figsize=(22, 10))
    data = np.array(data_nn)
    x = range(data.shape[1])
    axes.set_title(title)
    axes.set_xlabel(x_label)
    axes.set_ylabel(y_label)
    axes.errorbar(x, np.mean(data_nn, axis=0), yerr=np.sqrt(np.var(data_nn, axis=0)), fmt='o', label="NN MLMC", color="red")
    axes.errorbar(x, np.mean(data_mlmc, axis=0), yerr=np.sqrt(np.var(data_mlmc, axis=0)), fmt='o', label="MLMC", color="blue")
    fig.legend()
    fig.savefig("{}.pdf".format(title))
    fig.show()


def analyze_statistics(config):

    if not os.path.isdir(config['save_path']):
        print("dir not exists")
        exit()

    data_dict = load_statistics(config['save_path'])

    #print("data dict ", data_dict)

    # for key, data_dict in models_data.items():
    #     print("model: {}".format(key))

    mlmc_n_collected_all = []
    nn_n_collected_all = []
    n_ops_all = []
    n_ops_predict_all = []

    mlmc_times = []
    nn_times = []

    mlmc_l_vars = []
    nn_l_vars = []
    mlmc_vars_mse = []
    nn_vars_mse = []
    mlmc_means_mse = []
    nn_means_mse = []

    for i in range(len(data_dict["test_targets"])):
        # if i == 1:
        #     break
        predictions = data_dict["test_predictions"][i]
        targets = data_dict["test_targets"][i]
        train_predictions = data_dict["train_predictions"][i]
        train_targets = data_dict["train_targets"][i]
        val_predictions = data_dict["val_predictions"][i]
        val_targets = data_dict["val_targets"][i]
        l_0_predictions = data_dict["l_0_predictions"][i]
        l_0_targets = data_dict["l_0_targets"][i]
        l1_sample_time = data_dict["l1_sample_time"][i]
        l0_sample_time = data_dict["l0_sample_time"][i]
        total_steps = data_dict["total_steps"][i]

        print("total steps ", total_steps)

        mlmc_n_collected, nn_mlmc_n_collected, n_ops, n_ops_predict, orig_moments_mean, predict_moments_mean,\
        ref_moments_mean, orig_level_params, nn_level_params = process_mlmc(config['nn_hdf_path'],
                                                                            config['sampling_info_path'],
                                                                            config['ref_mlmc_file'], targets,
                       predictions, train_targets,
                       train_predictions,
                       val_targets, l_0_targets,
                       l_0_predictions, l1_sample_time, l0_sample_time,
                       nn_level=config['level'],
                       replace_level=config['replace_level'],
                        mlmc_hdf_file = config['mlmc_hdf_path'],
                       stats=True)

        mlmc_n_collected_all.append(mlmc_n_collected)
        nn_n_collected_all.append(nn_mlmc_n_collected)
        n_ops_all.append(n_ops)
        n_ops_predict_all.append(n_ops_predict)

        mlmc_times.append(np.sum(np.array(mlmc_n_collected) * np.array(n_ops)))
        nn_times.append(np.sum(np.array(nn_mlmc_n_collected) * np.array(n_ops_predict)))

        mlmc_l_vars.append(orig_moments_mean.l_vars)
        nn_l_vars.append(predict_moments_mean.l_vars)

        mlmc_vars_mse.append((ref_moments_mean.var - orig_moments_mean.var) ** 2)
        nn_vars_mse.append((ref_moments_mean.var - predict_moments_mean.var) ** 2)

        mlmc_means_mse.append((ref_moments_mean.mean - orig_moments_mean.mean) ** 2)
        nn_means_mse.append((ref_moments_mean.mean - predict_moments_mean.mean) ** 2)

    mlmc_total_time = np.mean(mlmc_times)
    nn_total_time = np.mean(nn_times)
    print("mlmc total time ", mlmc_total_time)
    print("nn total time ", nn_total_time)

    n_ops_mlmc_mean = np.mean(n_ops_all, axis=0)
    n_ops_nn_mean = np.mean(n_ops_predict_all, axis=0)

    print("n ops mlmc mean ", n_ops_mlmc_mean)
    print("n ops nn mean ", n_ops_nn_mean)

    mlmc_n_collected = np.mean(mlmc_n_collected_all, axis=0)
    nn_n_collected = np.mean(nn_n_collected_all, axis=0)

    print("mlmc n collected ", mlmc_n_collected_all)
    print("nn n collected all ", nn_n_collected_all)
    print("mlmc n collected ", mlmc_n_collected)
    print("nn n collected ", nn_n_collected)

    plt_var = plot.Variance()
    l_vars = np.mean(mlmc_l_vars, axis=0)
    print("np.squeeze(orig_level_params) ", orig_level_params)
    print("l vars ", l_vars)

    print("np.squeeze(orig_level_params) shape", orig_level_params.shape)
    print("l vars shape", l_vars.shape)
    plt_var.add_level_variances(np.squeeze(orig_level_params), l_vars)
    # plt_var.show(None)
    # plt_var.show("mlmc_vars")
    #
    # plt_var = plot.Variance()
    l_vars = np.mean(nn_l_vars, axis=0)
    print("nn l vars  ", l_vars)
    print("nn level parsm ", nn_level_params)
    level_params = np.squeeze(nn_level_params)
    level_params[0] *= 2
    plt_var.add_level_variances_nn(level_params, l_vars)
    plt_var.show(None)
    plt_var.show("nn_vars")

    plot_sse(nn_vars_mse, mlmc_vars_mse, title="moments_var")
    plot_sse(nn_means_mse, mlmc_means_mse, title="moments_mean")

    data_dict["test_targets"] = np.array(data_dict["test_targets"])
    data_dict["test_predictions"] = np.array(data_dict["test_predictions"])
    data_dict["train_targets"] = np.array(data_dict["train_targets"])
    data_dict["train_predictions"] = np.array(data_dict["train_predictions"])

    if data_dict["log"][0]:
        data_dict["test_targets"] = np.exp(data_dict["test_targets"])
        data_dict["test_predictions"] = np.exp(data_dict["test_predictions"])
        data_dict["train_targets"] = np.exp(data_dict["train_targets"])
        data_dict["train_predictions"] = np.exp(data_dict["train_predictions"])

        # print("test targets ", data_dict["test_targets"])
        # print("test predictions ", data_dict["test_predictions"])
        #
        # print("orig max vars ", data_dict["orig_max_vars"])
        # print("predict max vars ", data_dict["predict_max_vars"])

    # mean_orig_vars = np.mean(data_dict["orig_max_vars"], axis=0)
    # mean_predict_vars = np.mean(data_dict["predict_max_vars"], axis=0)
    total_steps = np.mean(data_dict["total_steps"])

    # print("mean orig vars ", mean_orig_vars)
    # print("mean predict vars ", mean_predict_vars)
    print("total steps ", total_steps)

    print("test targets ",  data_dict["test_targets"])
    print("test predictions ", data_dict["test_predictions"])
    print("test diff ", data_dict["test_predictions"] - data_dict["test_targets"])
    print("test diff squared ", (data_dict["test_predictions"] - data_dict["test_targets"])**2)

    test_MSE = np.mean((data_dict["test_predictions"] - data_dict["test_targets"])**2, axis=1)
    test_RMSE = np.sqrt(test_MSE)
    test_MAE = np.mean(np.abs(data_dict["test_predictions"] - data_dict["test_targets"]), axis=1)

    train_MSE = np.mean((data_dict["train_predictions"] - data_dict["train_targets"]) ** 2, axis=1)
    train_RMSE = np.sqrt(train_MSE)
    train_MAE = np.mean(np.abs( data_dict["train_predictions"] - data_dict["train_targets"]), axis=1)
    learning_times = data_dict["learning_times"]

    # plot_data(test_MSE, label="test MSE")
    # plot_data(test_MAE, label="test MAE")

    print("test_MSE ", test_MSE)

    print("NN moments MSE sum ",  np.sum(np.mean(nn_means_mse, axis=0)))

    print("mean test MSE ", np.mean(test_MSE))
    print("mean test RMSE ", np.mean(test_RMSE))
    print("mean test MAE ", np.mean(test_MAE))
    print("max test MSE ", np.max(test_MSE))
    print("max test RMSE ", np.max(test_RMSE))
    print("max test MAE ", np.max(test_MAE))

    print("mean train MSE ", np.mean(train_MSE))
    print("mean train RMSE ", np.mean(train_RMSE))
    print("mean train MAE ", np.mean(train_MAE))
    print("max train MSE ", np.max(train_MSE))
    print("max train RMSE ", np.max(train_RMSE))
    print("max train MAE ", np.max(train_MAE))

    print("mean learning time ", np.mean(learning_times))
    print("max learning time ", np.max(learning_times))

    print("######################################")


def run_GNN(config, stats=True, train=True, log=False):

    loss = MeanSquaredError()  # var_loss_function#
    accuracy_func = MSE_moments
    # loss = MeanAbsoluteError()
    # loss = MeanSquaredLogarithmicError()
    #loss = KLDivergence()
    # loss = total_loss_function
    optimizer = tf.optimizers.Adam(learning_rate=config['learning_rate'])
    batch_size = config['batch_size']#2000
    epochs = config['epochs']#1000
    hidden_regularization = None  # l2(2e-10)

    graph_creation_time = config['graph_creation_time']
    if graph_creation_time == 0:
        graph_creator_preproces_time = time.process_time()
        graph_creator(config['output_dir'], config['hdf_path'], config['mesh'], level=config['level'])
        graph_creation_time = time.process_time() - graph_creator_preproces_time
        print("graph creation time ", graph_creation_time)
        #exit()

    preprocess_start_time = time.process_time()
    # Load data
    data = FlowDataset(output_dir=config['output_dir'], level=config['level'], log=log)
    data = data#[:10000]

    #print("len data ", len(data))
    data.shuffle()
    preprocess_time = time.process_time() - preprocess_start_time
    #print("preproces time ", preprocess_time)
    preprocess_time = preprocess_time + graph_creation_time
    print("total preprocess time ", preprocess_time)

    learning_time_start = time.process_time()
    data.a = config['conv_layer'].preprocess(data.a)
    data.a = sp_matrix_to_sp_tensor(data.a)
    #train_data_len = int(len(data) * 0.8)
    train_data_len = config['n_train_samples']
    # Train/valid/test split
    data_tr, data_te = data[:train_data_len], data[train_data_len:]

    gnn = config['get_gnn']()[0]
    print("gnn ", gnn)

    if hasattr(gnn._loss,'__name__'):
        if gnn._loss.__name__ == "MSE_moments":
            tr_output = [g.y for g in data_tr]
            n_moments = 3
            quantile = 0.01
            domain = np.percentile(tr_output, [100 * quantile, 100 * (1 - quantile)])
            moments_fn = Legendre_tf(n_moments, domain)
            #accuracy_func = MSE_moments(moments_fn=moments_fn)
            gnn._loss = MSE_moments(moments_fn=moments_fn)

    if hasattr(gnn._final_loss,'__name__'):
        if gnn._final_loss.__name__ == "MSE_moments":
            tr_output = [g.y for g in data_tr]
            loss_params = config["loss_params"]
            #n_moments = 3
            quantile = loss_params["quantile"]
            domain = np.percentile(tr_output, [100 * quantile, 100 * (1 - quantile)])
            #moments_fn = Legendre_tf(n_moments, domain)
            loss_params['domain'] = domain
            #accuracy_func = MSE_moments(moments_fn=moments_fn)
            gnn._loss_params = loss_params
            #gnn._final_loss = MSE_moments(moments_fn=moments_fn)


    np.random.shuffle(data_tr)
    val_data_len = int(len(data_tr) * config['val_samples_ratio'])
    data_tr, data_va = data_tr[:-val_data_len], data_tr[-val_data_len:]

    # print("data_tr len ", len(data_tr))
    # print("data_va len ", len(data_va))
    # print("data_te len ", len(data_te))

    # We use a MixedLoader since the dataset is in mixed mode
    loader_tr = MixedLoader(data_tr, batch_size=batch_size, epochs=epochs)
    loader_va = MixedLoader(data_va, batch_size=batch_size)
    loader_te = MixedLoader(data_te, batch_size=batch_size)
    #
    if gnn is None:
        gnn = GNN(loss=loss, optimizer=optimizer, conv_layer=config['conv_layer'], output_activation=abs_activation,
                  hidden_activation='relu', patience=150, hidden_reqularizer=hidden_regularization,
                  model=config['model'], accuracy_func=accuracy_func)  # tanh takes to much time
        # ideally patience = 150
        # batch_size 500, ideally 500 epochs, patience 35

    if train:
        # gnn.run_eagerly = True
        train_targets = gnn.fit(loader_tr, loader_va, loader_te)

    # states = gnn._states
    # if len(states) > 0:
    #     min_key = np.min(list(states.keys()))
    #     gnn = states[min_key]

    train_targets, train_predictions = gnn.predict(loader_tr)
    train_predictions = np.squeeze(train_predictions)

    val_targets, val_predictions = gnn.predict(loader_va)
    val_predictions = np.squeeze(val_predictions)

    #val_targets = gnn.val_targets
    total_steps = gnn._total_n_steps

    targets, predictions = gnn.predict(loader_te)
    predictions = np.squeeze(predictions)
    learning_time = time.process_time() - learning_time_start
    #print("learning time ", learning_time)

    targets = np.array(targets)
    predictions = np.array(predictions)

    #print("MSE ", np.mean((predictions-targets)**2))

    if log:
        targets = np.exp(targets)
        predictions = np.exp(predictions)

    if not stats:
        analyze_results(targets, predictions)
        plot_loss(gnn._train_loss, gnn._val_loss)
        analyze_results(targets, predictions)

        import matplotlib.pyplot as plt

        plt.hist(targets, bins=50, alpha=0.5, label='target', density=True)
        plt.hist(predictions, bins=50, alpha=0.5, label='predictions', density=True)

        # plt.hist(targets - predictions, bins=50, alpha=0.5, label='predictions', density=True)
        plt.legend(loc='upper right')
        # plt.xlim(-0.5, 1000)
        plt.yscale('log')
        plt.show()

    #predict_l_0_start_time = time.process_time()
    l_0_targets, l_0_predictions, predict_l_0_time = predict_level_zero(gnn, config['l_0_output_dir'],
                                                                        config['l_0_hdf_path'], config['mesh'],
                                                                        config['conv_layer'], batch_size, log,
                                                                        stats=stats,
                                                                        corr_field_config=config['corr_field_config'])
    #predict_l_0_time = time.process_time() - predict_l_0_start_time
    if stats:
        l1_sample_time = preprocess_time / len(data) + learning_time / len(data)
        l0_sample_time = predict_l_0_time / len(l_0_targets)

        # print("targets ", targets)
        # print("predictions ", predictions)

        # orig_max_vars, predict_max_vars = process_mlmc(hdf_path, sampling_info_path, ref_mlmc_file, targets, predictions, train_targets,
        #              train_predictions,
        #              val_targets, l_0_targets,
        #              l_0_predictions, l1_sample_time, l0_sample_time, nn_level=level, replace_level=replace_level,
        #                                                stats=stats)

        return gnn._model, targets, predictions, learning_time, train_targets, train_predictions,\
               val_targets, val_predictions, l_0_targets, l_0_predictions, l1_sample_time, l0_sample_time, total_steps, gnn._current_patience

    save_times(config['save_path'], False, (preprocess_time, len(data)), learning_time, (predict_l_0_time, len(l_0_targets)))
    save_load_data(config['save_path'], False, targets, predictions, train_targets, train_predictions, val_targets, l_0_targets,
                   l_0_predictions)


def predict_level_zero(nn, output_dir, hdf_path, mesh, conv_layer, batch_size=1000, log=False, stats=False, corr_field_config=None):
    #graph_creator(output_dir, hdf_path, mesh, level=0)
    # Load data

    sample_time = 0
    if corr_field_config:
        sample_time = corr_field_sample_time(mesh, corr_field_config)

    data = FlowDataset(output_dir=output_dir, log=log)#, mesh=mesh, corr_field_config=corr_field_config)
    #data = data  # [:10000]

    predict_time_start = time.process_time()
    data.a = conv_layer.preprocess(data.a)
    data.a = sp_matrix_to_sp_tensor(data.a)

    loader_te = MixedLoader(data, batch_size=batch_size)

    targets, predictions = nn.predict(loader_te)
    predictions = np.squeeze(predictions)

    if not stats:
        analyze_results(targets, predictions)

    if log:
        targets = np.exp(targets)
        predictions = np.exp(predictions)
    if not stats:
        analyze_results(targets, predictions)

    predict_time = time.process_time() - predict_time_start

    return targets, predictions, predict_time + sample_time*len(data)


def save_times(path, load=False, preprocess=None, learning_time=None, predict_l_0=None):
    if load:
        preprocess_time = None
        preprocess_n = None
        predict_time = None
        predict_n = None
        if os.path.exists(os.path.join(path, "preprocess_time.npy")):
            preprocess_time = np.load(os.path.join(path, "preprocess_time.npy"))
        if os.path.exists(os.path.join(path, "preprocess_n.npy")):
            preprocess_n = np.load(os.path.join(path, "preprocess_n.npy"))
        if os.path.exists(os.path.join(path, "learning_time.npy")):
            learning_time = np.load(os.path.join(path, "learning_time.npy"))
        if os.path.exists(os.path.join(path, "predict_l_0_time.npy")):
            predict_time = np.load(os.path.join(path, "predict_l_0_time.npy"))
        if os.path.exists(os.path.join(path, "predict_l_0_n.npy")):
            predict_n = np.load(os.path.join(path, "predict_l_0_n.npy"))
        return preprocess_time, preprocess_n, learning_time, predict_time, predict_n
    else:
        if preprocess is not None:
            np.save(os.path.join(path, "preprocess_time"), preprocess[0])
            np.save(os.path.join(path, "preprocess_n"), preprocess[1])
        if learning_time is not None:
            np.save(os.path.join(path, "learning_time"), learning_time)
        if preprocess is not None:
            np.save(os.path.join(path, "predict_l_0_time"), predict_l_0[0])
            np.save(os.path.join(path, "predict_l_0_n"), predict_l_0[1])


def save_load_data(path, load=False, targets=None, predictions=None, train_targets=None, train_predictions=None,
                   val_targets=None, l_0_targets=None,
                   l_0_predictions=None):
    if load:
        if os.path.exists(os.path.join(path, "targets.npy")):
            targets = np.load(os.path.join(path, "targets.npy"))
        if os.path.exists(os.path.join(path, "predictions.npy")):
            predictions = np.load(os.path.join(path, "predictions.npy"))
        if os.path.exists(os.path.join(path, "train_targets.npy")):
            train_targets = np.load(os.path.join(path, "train_targets.npy"))
        if os.path.exists(os.path.join(path, "train_predictions.npy")):
            train_predictions = np.load(os.path.join(path, "train_predictions.npy"))
        if os.path.exists(os.path.join(path, "val_targets.npy")):
            val_targets = np.load(os.path.join(path, "val_targets.npy"))
        if os.path.exists(os.path.join(path, "l_0_targets.npy")):
            l_0_targets = np.load(os.path.join(path, "l_0_targets.npy"))
        if os.path.exists(os.path.join(path, "l_0_predictions.npy")):
            l_0_predictions = np.load(os.path.join(path, "l_0_predictions.npy"))
        return targets, predictions, train_targets, train_predictions, val_targets, l_0_targets, l_0_predictions
    else:
        if targets is not None:
            np.save(os.path.join(path, "targets"), targets)
        if predictions is not None:
            np.save(os.path.join(path, "predictions"), predictions)
        if train_targets is not None:
            np.save(os.path.join(path, "train_targets"), train_targets)
        if train_predictions is not None:
            np.save(os.path.join(path, "train_predictions"), train_predictions)
        if val_targets is not None:
            np.save(os.path.join(path, "val_targets"), val_targets)
        if l_0_targets is not None:
            np.save(os.path.join(path, "l_0_targets"), l_0_targets)
        if l_0_predictions is not None:
            np.save(os.path.join(path, "l_0_predictions"), l_0_predictions)


def process_results(hdf_path, sampling_info_path, ref_mlmc_file, save_path, nn_level, replace_level):
    targets, predictions, train_targets, train_predictions, val_targets, l_0_targets, l_0_predictions = save_load_data(
        save_path, load=True)
    preprocess_time, preprocess_n, learning_time, predict_l_0_time, predict_l_0_n = save_times(save_path, load=True)

    l1_sample_time = preprocess_time / preprocess_n + learning_time / preprocess_n
    l0_sample_time = predict_l_0_time / predict_l_0_n

    print("preprocess_time ", preprocess_time)
    print("preprocess_n ", preprocess_n)
    print("learning_time ", learning_time)
    print("predict_l_0_time ", predict_l_0_time)
    print("predict_l_0_n ", predict_l_0_n)

    print("l1 sample time ", l1_sample_time)
    print("l0 sample time ", l0_sample_time)

    print("len targets ", len(targets))
    print("len predictions ", len(predictions))

    print("len train targets ", len(train_targets))
    print("len val targets ", len(val_targets))

    process_mlmc(hdf_path, sampling_info_path, ref_mlmc_file, targets, predictions, train_targets, train_predictions,
                 val_targets, l_0_targets,
                 l_0_predictions, l1_sample_time, l0_sample_time, nn_level=nn_level, replace_level=replace_level)